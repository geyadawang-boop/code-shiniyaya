class OperationCancelled(Exception):
    """Exception raised when an async operation is cancelled via a cancel token.

    Inherits from Exception (not BaseException) so that standard
    ``except Exception:`` handlers can catch and handle it properly.
    """
    pass

def ensure_not_cancelled(cancel_check):
    """Check the cancel token and raise OperationCancelled if requested.

    Args:
        cancel_check: A callable that returns True if cancellation has been
                      requested, or None/falsey if cancellation is not enabled.
    """
    if cancel_check and cancel_check():
        raise OperationCancelled()
