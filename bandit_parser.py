import argparse
import json
import os.path
import sys


class BanditResult:
    def __init__(self, rs):
        self.code = rs["code"]
        self.filename = rs["filename"]
        self.issue_confidence = rs["issue_confidence"]
        self.issue_severity = rs["issue_severity"]
        self.issue_text = rs["issue_text"]
        self.line_number = rs["line_number"]
        self.line_range = rs["line_range"]
        self.more_info = rs["more_info"]
        self.test_id = rs["test_id"]
        self.test_name = rs["test_name"]

    def __str__(self):
        return "{}(s:{}-c:{})  {}:{}".format(self.test_name,
                                             self.issue_severity,
                                             self.issue_confidence,
                                             self.filename,
                                             self.line_number)


class Bandit:
    def __init__(self, d):
        self.errors = d["errors"]
        self.timestamp = d["generated_at"]
        self.metrics = d["metrics"]
        self.results = []
        try:
            for rs in d["results"]:
                r = BanditResult(rs)
                self.results.append(r)
        except KeyError as e:
            print("failed to initialise BanditResult: " + str(e))
            sys.exit(-1)

    def __str__(self):
        s = self.timestamp + '\n'
        i = 1
        for r in bandit.results:
            s += (str(i) + ": " + str(r) + '\n')
            i += 1
        return s


def parse_args():
    parser = argparse.ArgumentParser(description="Parser for bandit output")
    parser.add_argument("in_file", help="the bandit output file to parse")
    parser.add_argument("out_file", help="the issues output file to save")
    parser.add_argument("-d", "--diagnostic",
                        dest="diagnostic",
                        action="store_true",
                        help="enable diagnostic mode")
    return parser.parse_args()


def diagnose(s):
    if args.diagnostic:
        print(s)


def write_issue(f, r, i):
    f.write("index: {}\\n".format(i))
    f.write("issue_id: {} {}\\n".format(r.test_id, r.test_name))
    f.write("issue_text: {}\\n".format(r.issue_text))
    f.write("severity: {}\\n".format(r.issue_severity))
    f.write("confidence: {}\\n".format(r.issue_confidence))
    f.write("file: {}\\n".format(r.filename))
    f.write("line: {}\\n".format(r.line_number))
    f.write("code: {}\\n".format(r.code))
    f.write("\\n")


if __name__ == "__main__":
    args = parse_args()
    if not os.path.exists(args.in_file):
        print("bandit output file not found!")
        sys.exit(-1)
    diagnose(args.in_file)

    if os.path.exists(args.out_file):
        print("issue output file already exist!")
        sys.exit(-1)
    diagnose(args.out_file)

    try:
        with open(args.in_file) as f:
            data = json.load(f)
    except ValueError as e:
        print("failed to load json file: " + str(e))
        sys.exit(-1)
    diagnose(data)

    try:
        bandit = Bandit(data)
    except KeyError as e:
        print("failed to initialise Bandit: " + str(e))
        sys.exit(-1)
    diagnose(bandit)

    with open(args.out_file, 'w') as f:
        i = 1
        for r in bandit.results:
            write_issue(f, r, i)
            i += 1

    if len(bandit.results):
        sys.exit(1)

    sys.exit(0)
