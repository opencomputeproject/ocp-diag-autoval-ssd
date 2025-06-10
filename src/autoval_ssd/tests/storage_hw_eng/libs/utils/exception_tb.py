# pyre-unsafe
import io
import traceback


def get_traceback_str():
    """
    Create a string with the Traceback.

    Returns:
        The string representation of the traceback.
    """
    try:
        buffer = io.StringIO()
        traceback.print_exc(file=buffer)
        msg = f"{buffer.getvalue()}"
        buffer.close()
    except Exception as e:
        return f"Failed to get traceback -- {type(e)} : {e}"

    return msg
