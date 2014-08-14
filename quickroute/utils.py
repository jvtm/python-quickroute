'''
Python QuickRoute utility functions
'''

from datetime import datetime, timedelta
import json


class DateTimeEncoder(json.JSONEncoder):
    """ Replacement JSON encoder supporting datetime and timedelta objects """
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, timedelta):
            return str(obj)
        else:
            return super(DateTimeEncoder, self).default(obj)
