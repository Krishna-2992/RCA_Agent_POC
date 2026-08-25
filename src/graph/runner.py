"""Runs the compiled LangGraph on a worker thread and streams progress events.

`graph.invoke()` blocks until the entire workflow is done, which leaves the UI
with nothing to show for minutes at a time. Streaming on a background thread
lets the caller repaint on a timer (a "tick" event) even while a single node -
typically the GitHub investigator - is still working.
"""

import queue
import threading
import time
import traceback


# The graph now runs on a worker thread, so a Streamlit rerun can leave a run
# orphaned and still executing. This lock stops a second run from starting on
# top of it and competing for the same clients and API quota.

_run_lock = threading.Lock()

_run_started_at = None


def describe_error(error):
    """One-line cause. Some client exceptions stringify to nothing useful -
    a Qdrant read timeout, for instance, is just the word "timed out"."""

    text = str(error).strip()

    if not text:
        text = "no error message"

    return f"{type(error).__name__}: {text}"


def _attach_streamlit_context(thread):
    """Keeps Streamlit from warning about the worker thread (best effort)."""

    try:
        from streamlit.runtime.scriptrunner import add_script_run_ctx

        add_script_run_ctx(
            thread
        )

    except Exception:
        pass


def stream_workflow(graph, input_state, tick_seconds=0.4):
    """Yields progress events until the workflow finishes.

    Event shapes:
        {"type": "node_end", "node": str, "delta": dict}
        {"type": "state", "state": dict}
        {"type": "tick"}
        {"type": "busy", "elapsed": float}
        {"type": "final", "state": dict}
        {"type": "error", "error": Exception, "traceback": str}
    """

    global _run_started_at

    if not _run_lock.acquire(blocking=False):

        yield {
            "type": "busy",
            "elapsed": time.time() - (_run_started_at or time.time())
        }

        return

    _run_started_at = time.time()

    events = queue.Queue()

    def worker():

        final_state = {}

        try:

            for mode, chunk in graph.stream(
                input_state,
                stream_mode=["updates", "values"]
            ):

                if mode == "updates":

                    for node, delta in (chunk or {}).items():

                        events.put(
                            {
                                "type": "node_end",
                                "node": node,
                                "delta": delta
                            }
                        )

                elif mode == "values":

                    if isinstance(chunk, dict):

                        final_state = chunk

                        events.put(
                            {
                                "type": "state",
                                "state": chunk
                            }
                        )

            events.put(
                {
                    "type": "final",
                    "state": final_state
                }
            )

        except Exception as error:

            events.put(
                {
                    "type": "error",
                    "error": error,
                    "traceback": traceback.format_exc()
                }
            )

        finally:

            _run_lock.release()

    thread = threading.Thread(
        target=worker,
        daemon=True
    )

    _attach_streamlit_context(
        thread
    )

    try:
        thread.start()

    except BaseException:

        _run_lock.release()

        raise

    while True:

        try:
            event = events.get(
                timeout=tick_seconds
            )

        except queue.Empty:

            yield {
                "type": "tick"
            }

            continue

        yield event

        if event["type"] in ("final", "error"):
            break
