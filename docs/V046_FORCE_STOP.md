# v0.4.6 ComfyUI Force Stop

v0.4.6 adds a Force Stop recovery path on the Device page for cases where ComfyUI is still consuming GPU or system memory but normal Stop cannot run because the Panel has no process record.

## UI behavior

- When ComfyUI was started by the current Panel and its process record is valid, the Device page keeps the normal `Stop` action.
- When no Panel process record exists but the current ComfyUI listener can be safely identified, the existing red Stop button changes to `Force Stop`.
- If the ComfyUI API is already unresponsive, Force Stop remains available as long as the listener process can still be safely identified.

## Safety boundary

Force Stop does not search by process name and terminate arbitrary `python.exe` processes. It is allowed only when all of the following are true:

1. exactly one matching process is listening on the configured ComfyUI port;
2. its executable matches the Python executable in `[comfyui.control] start_command`;
3. its Python entrypoint matches the configured ComfyUI `main.py`;
4. its working directory matches the configured ComfyUI working directory.

Optional launch flags such as `--use-sage-attention` are intentionally not part of the fallback identity. This lets the Panel recover an older ComfyUI process that was started before those optional flags were added or removed from `start_command`.

If the executable, entrypoint, working directory, or listener is ambiguous, the Panel refuses the force-stop request.

Force Stop terminates the verified ComfyUI main process and its verified descendants, and active Panel jobs are moved to an interrupted state. The existing safety rules for normal Stop remain unchanged.
