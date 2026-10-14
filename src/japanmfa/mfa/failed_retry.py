"""Additional search only after the pinned MFA decoder's original search fails."""
from __future__ import annotations

import logging
from pathlib import Path
import runpy
import shutil
import sys


def wrap_compiled_alignment(align):
    def wrapped(transition_model, acoustic_model, graph, features, **parameters):
        pristine = graph.Copy()
        result = align(transition_model, acoustic_model, graph, features, **parameters)
        if result[4] or parameters.get("beam") != 10 or parameters.get("retry_beam") != 40:
            return result
        retry = align(transition_model, acoustic_model, pristine, features,
                      **{**parameters, "retry_beam": 160})
        logging.getLogger("kalpy.align").info(
            "Additional failed-only retry10/160 after unsuccessful10/40: successful=%s",
            retry[4],
        )
        return retry
    return wrapped


def failed_retry_command(command):
    if len(command) != 1:
        raise ValueError("failed-only retry requires one pinned Python MFA executable")
    executable = Path(shutil.which(command[0]) or command[0]).resolve()
    header = executable.open(encoding="utf-8").readline().strip()
    interpreter = header[2:] if header.startswith("#!/") else ""
    if "python" not in Path(interpreter).name or " " in interpreter:
        raise ValueError("failed-only retry requires an absolute Python shebang")
    return [interpreter, str(Path(__file__).resolve()), str(executable)]


def main():
    command = sys.argv[1:]
    if len(command) < 2 or command[1] != "align" or command[-2:] != ["--num_jobs", "1"]:
        raise ValueError("failed-only retry is limited to one-job MFA alignment")
    import kalpy.gmm.align as alignment
    alignment.gmm_align_compiled = wrap_compiled_alignment(alignment.gmm_align_compiled)
    sys.argv = command
    runpy.run_path(command[0], run_name="__main__")


if __name__ == "__main__":
    main()
