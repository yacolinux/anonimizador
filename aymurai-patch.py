import json
import numpy

class _NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (numpy.integer,)):
            return int(obj)
        elif isinstance(obj, (numpy.floating,)):
            return float(obj)
        elif isinstance(obj, (numpy.ndarray,)):
            return obj.tolist()
        return super().default(obj)

_numpy_encoder = _NumpyEncoder()
json.encoder.JSONEncoder.default = _numpy_encoder.default

# Also patch json.dumps to use cls by default - more robust
_original_dumps = json.dumps
def _patched_dumps(obj, **kwargs):
    if 'cls' not in kwargs:
        kwargs['cls'] = _NumpyEncoder
    return _original_dumps(obj, **kwargs)
json.dumps = _patched_dumps
