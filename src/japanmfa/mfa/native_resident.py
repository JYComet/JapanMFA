"""One-job native MFA service; preserve native decoders and model content identity."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
from collections import OrderedDict
from multiprocessing.connection import Client, Listener


ACCENT_RECOVERY_SOURCE = Path(__file__).resolve().parents[1] / "accent/model_recovery.py"
ACCENT_CODE = """
import json,sys,traceback
import chainer,jaconv
from tdmelodic.nn.convert import Converter
from tdmelodic.nn.lang.japanese.kana.mora_sep import sep_katakana2mora
sys.path.insert(0, '/tmp')
from japanmfa_accent_model_recovery import choose_repair, needs_recovery

converter=Converter()
for line in sys.stdin:
    try:
        request=json.loads(line)
        outputs=[]; errors={}; repairs={}; repair_errors={}
        for index,value in enumerate(request['lines']):
            try:
                surface,yomi=value.strip().split(',')
                output=converter.sy2a(surface,yomi)
                if not output.strip(): errors[str(index)]='empty_output'
                else:
                    normalized=jaconv.hira2kata(jaconv.normalize(yomi,'NFKC'))
                    morae=tuple(sep_katakana2mora(normalized))
                    if needs_recovery(output,morae):
                        try:
                            analyses,rank,distance=converter.unidic.get_n_best(surface,normalized)
                            entries=analyses[rank[0]] if rank and distance==0 else ()
                            if len(entries)==1:
                                s_np,y_np=converter.add_batch_dim(*converter.encode_sy(surface,normalized))
                                with chainer.using_config('debug',False), chainer.using_config('type_check',False), chainer.using_config('train',False):
                                    logits,_=converter.model.net(s_np,y_np,y_np[0]*0)
                                scores=logits.data[0,:,:len(morae)].T.tolist()
                                repair=choose_repair(output,surface,normalized,morae,scores,entries)
                                if repair is not None:
                                    output=repair['marked']
                                    repairs[str(index)]=repair
                        except Exception:
                            repair_errors[str(index)]=traceback.format_exc()[-2000:]
            except Exception:
                if not request['partial']: raise
                output=''; errors[str(index)]='command_failed'
            outputs.append(output)
        print(json.dumps({'code':0,'outputs':outputs,'errors':errors,'repairs':repairs,
                          'repair_errors':repair_errors},ensure_ascii=False),flush=True)
    except Exception:
        print(json.dumps({'code':1,'error':traceback.format_exc()},ensure_ascii=False),flush=True)
"""


class ContentModelCache:
    def __init__(self, read, limit=4):
        self.read = read
        self.limit = limit
        self.values = OrderedDict()
        self.hits = self.loads = 0

    def __call__(self, path):
        key = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        if key in self.values:
            self.hits += 1
            self.values.move_to_end(key)
            return self.values[key]
        value = self.read(path)
        self.loads += 1
        self.values[key] = value
        if len(self.values) > self.limit:
            self.values.popitem(last=False)
        return value


def validate_request(args, scope):
    if not args or args[0] not in {"align", "g2p", "accent", "accent-partial"}:
        raise ValueError("unsupported resident operation")
    if args[0] in {"accent", "accent-partial"}:
        if len(args) != 1:
            raise ValueError("accent takes stdin only")
        return
    if args[0] == "align":
        if args[-2:] != ["--num_jobs", "1"] or args[3] != "japanese_mfa":
            raise ValueError("resident alignment requires pinned model and one job")
        paths = [args[1], args[2], args[4], args[args.index("--temporary_directory") + 1]]
    else:
        if args[2] != "japanese_mfa":
            raise ValueError("resident G2P requires pinned model")
        paths = [args[1], args[3]]
    scope = Path(scope).resolve()
    for value in paths:
        if scope not in Path(value).resolve().parents:
            raise ValueError("native request escapes this job")


@contextlib.contextmanager
def sqlite_import_wait(scope):
    """Give this native job's SQLite imports time to outlive a short reader."""
    original = subprocess.check_call
    scope = Path(scope).resolve()

    def check_call(*popenargs, **kwargs):
        command = popenargs[0] if popenargs else kwargs.get("args")
        if (isinstance(command, (list, tuple)) and len(command) >= 3
                and Path(command[0]).name == "sqlite3"
                and scope in Path(command[1]).resolve().parents
                and any(str(value).startswith(".import ") for value in command[2:])):
            command = [*command[:2], "--cmd", ".timeout 5000", *command[2:]]
            if popenargs:
                popenargs = (command, *popenargs[1:])
            else:
                kwargs["args"] = command
        return original(*popenargs, **kwargs)

    subprocess.check_call = check_call
    try:
        yield
    finally:
        subprocess.check_call = original


def receive_request(connection):
    try:
        return connection.recv()
    except (EOFError, ConnectionResetError):
        return None


def send_response(connection, response):
    try:
        connection.send(response)
        return True
    except (BrokenPipeError, ConnectionResetError):
        return False


def serve(socket, scope, role="all"):
    import kalpy.gmm.align as alignment
    import kalpy.gmm.utils as utils
    from montreal_forced_aligner.command_line.mfa import mfa_cli
    from montreal_forced_aligner.g2p.generator import PyniniGenerator
    from japanmfa.mfa.failed_retry import wrap_compiled_alignment

    original_read = utils.read_gmm_model
    models = ContentModelCache(original_read)
    # MFA workers import this function in several modules. Replace only those
    # exact references inside this private process, never the installed files.
    for module in tuple(sys.modules.values()):
        if getattr(module, "read_gmm_model", None) is original_read:
            module.read_gmm_model = models
    alignment.gmm_align_compiled = wrap_compiled_alignment(alignment.gmm_align_compiled)
    original_setup = PyniniGenerator.setup
    g2p = {}
    g2p_loads = g2p_hits = 0

    def setup(instance):
        nonlocal g2p_loads, g2p_hits
        key = (hashlib.sha256(Path(instance.g2p_model.fst_path).read_bytes()).hexdigest(),
               json.dumps(instance.g2p_model.meta, sort_keys=True, default=lambda value: sorted(value)),
               instance.num_pronunciations, instance.g2p_threshold)
        if key not in g2p:
            original_setup(instance)
            g2p[key] = (instance.fst, instance.input_token_type,
                        instance.output_token_type, instance.rewriter)
            g2p_loads += 1
        else:
            (instance.fst, instance.input_token_type,
             instance.output_token_type, instance.rewriter) = g2p[key]
            g2p_hits += 1
    PyniniGenerator.setup = setup

    socket = Path(socket)
    socket.parent.mkdir(parents=True, exist_ok=True)
    if socket.exists():
        raise ValueError("resident socket already exists; inspect owner first")
    accent = None
    started = time.time()
    try:
        with Listener(str(socket), family="AF_UNIX") as listener:
            os.chmod(socket, 0o600)
            while True:
                with listener.accept() as connection:
                    request = receive_request(connection)
                    if request is None:
                        continue
                    if request == {"shutdown": True}:
                        send_response(connection, {"code": 0, "stdout": "", "stderr": ""})
                        break
                    output, error = io.StringIO(), io.StringIO()
                    begin = time.monotonic()
                    code = 0
                    accent_repairs = {}
                    accent_repair_errors = {}
                    try:
                        args = request["args"]
                        validate_request(args, scope)
                        if role == "prepare" and args[0] == "align":
                            raise ValueError("preparation service cannot align")
                        if args[0] in {"accent", "accent-partial"}:
                            if accent is None:
                                accent = subprocess.Popen(
                                    ["docker", "run", "--rm", "-i", "--mount",
                                     f"type=bind,src={ACCENT_RECOVERY_SOURCE},dst=/tmp/japanmfa_accent_model_recovery.py,readonly",
                                     "--entrypoint", "python",
                                     os.environ.get("JAPANMFA_ACCENT_MODEL_ID", "japanmfa-tdmelodic:e7fdb63f85bb"), "-u", "-c", ACCENT_CODE],
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=sys.stderr, text=True)
                            accent.stdin.write(json.dumps({"lines": request["stdin"].splitlines(), "partial": args[0] == "accent-partial"}, ensure_ascii=False) + "\n")
                            accent.stdin.flush()
                            line = accent.stdout.readline()
                            if not line:
                                raise RuntimeError("resident accent process exited")
                            result = json.loads(line)
                            code = result["code"]
                            accent_repairs = result.get("repairs", {})
                            accent_repair_errors = result.get("repair_errors", {})
                            if args[0] == "accent-partial" and code == 0:
                                output.write(json.dumps({"outputs": result["outputs"], "errors": result["errors"],
                                                         "repairs": accent_repairs}, ensure_ascii=False))
                            else:
                                output.write("\n".join(result.get("outputs", [])) + ("\n" if code == 0 else ""))
                            error.write(result.get("error", ""))
                        else:
                            wait = (sqlite_import_wait(args[args.index("--temporary_directory") + 1])
                                    if args[0] == "align" else contextlib.nullcontext())
                            with wait, contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
                                result = mfa_cli.main(args=args, standalone_mode=False)
                                if isinstance(result, int):
                                    code = result
                    except Exception:
                        code = 1
                        traceback.print_exc(file=error)
                    response = {"code": code, "stdout": output.getvalue(), "stderr": error.getvalue(),
                                "pid": os.getpid(), "seconds": time.monotonic() - begin,
                                "model_loads": models.loads, "model_hits": models.hits,
                                "g2p_loads": g2p_loads, "g2p_hits": g2p_hits,
                                "accent_repairs": accent_repairs,
                                "accent_repair_errors": accent_repair_errors}
                    Path(str(socket) + ".status.json").write_text(json.dumps({
                        **{k: v for k, v in response.items() if k not in {"stdout", "stderr"}},
                        "operation": request["args"][0], "at": time.time(), "started_at": started,
                        "accent_pid": None if accent is None else accent.pid,
                        "model_sha256": list(models.values)}))
                    with Path(str(socket) + ".requests.jsonl").open("a") as receipt:
                        receipt.write(json.dumps({**response, "args": request["args"], "at": time.time()}, ensure_ascii=False) + "\n")
                    send_response(connection, response)
    finally:
        if accent is not None:
            accent.stdin.close()
            try:
                accent.wait(timeout=5)
            except subprocess.TimeoutExpired:
                accent.terminate()
                accent.wait()
        socket.unlink(missing_ok=True)


def main():
    operation, socket, *args = sys.argv[1:]
    if operation == "serve":
        serve(socket, args[0], args[1] if len(args) > 1 else "all")
        return 0
    with Client(socket, family="AF_UNIX") as connection:
        connection.send({"shutdown": True} if operation == "stop" else
                        {"args": args, "stdin": sys.stdin.read() if args in (["accent"], ["accent-partial"]) else ""})
        response = connection.recv()
    sys.stdout.write(response["stdout"])
    sys.stderr.write(response["stderr"])
    return response["code"]


if __name__ == "__main__":
    raise SystemExit(main())
