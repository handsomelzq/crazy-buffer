"""Launch only on the IPv4 loopback interface, without telemetry."""
from pathlib import Path
import sys


def main():
    from streamlit.web import cli
    sys.argv = ['streamlit', 'run', str(Path(__file__).with_name('app.py')),
                '--server.address=127.0.0.1', '--browser.gatherUsageStats=false',
                '--server.maxUploadSize=20', '--server.headless=true',
                '--theme.base=light', '--theme.primaryColor=#295b4c',
                '--theme.backgroundColor=#f6f7f3',
                '--theme.secondaryBackgroundColor=#edf1e9',
                '--theme.textColor=#243f36']
    raise SystemExit(cli.main())
