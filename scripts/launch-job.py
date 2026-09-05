#!/usr/bin/env python3
"""Run guided setup and report a safe failure, without exposing provider credentials."""
import json, pathlib, sys
import install

def main():
    try:
        install.main()
    except Exception:
        try:
            release=json.loads((pathlib.Path(__file__).resolve().parents[1]/'release.json').read_text())
            install.signed_request(release,'/deployment-status',{'installation':install.os.environ['KISS_INSTALLATION_ID'],'phase':'failed'})
        except Exception: pass
        print('Setup could not finish. Return to your KISS Company setup page or contact Yuma support.',file=sys.stderr)
        return 1
    return 0
if __name__ == '__main__': sys.exit(main())
