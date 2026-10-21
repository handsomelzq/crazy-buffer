"""Launch only on the IPv4 loopback interface, without telemetry."""
from pathlib import Path
import sys


def main():
    from streamlit.web import cli
    sys.argv = ['streamlit', 'run', str(Path(__file__).with_name('app.py')),
                '--server.address=127.0.0.1', '--browser.gatherUsageStats=false',
                '--server.maxUploadSize=20', '--server.headless=true']
    raise SystemExit(cli.main())
