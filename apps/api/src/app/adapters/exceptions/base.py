
class ConnectorError(RuntimeError):
    pass

class UpstreamError(ConnectorError):
    pass

class NotFound(ConnectorError):
    pass
