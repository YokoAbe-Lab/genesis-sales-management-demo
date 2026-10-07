"""Launch the original local-only server from this repository."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'app'))
from sales_server import make_server

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8773)
    args = parser.parse_args()
    server = make_server(args.port)
    print(f'Genesis: http://127.0.0.1:{server.server_port}/', flush=True)
    print(f'Sales: http://127.0.0.1:{server.server_port}/sales', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
