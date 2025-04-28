# pyre-unsafe
import re


class DmesgCheck:
    def __init__(self, dmesg_regexes):
        self.compiled_regex = [re.compile(regex) for regex in dmesg_regexes]

    def check(self, dmesg, ts_only=False):
        errors = []
        for ts, entry in dmesg.items():
            for regex in self.compiled_regex:
                if regex.search(entry.raw) is not None:
                    if ts_only:
                        errors.append(ts)
                    else:
                        errors.append((ts, entry))
                    break

        return errors
