import argparse
import json
import os
import sys

from pathlib import Path
from PyQt5.QtCore import QStandardPaths, QTimer, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtNetwork import QLocalServer, QLocalSocket
from PyQt5.QtWidgets import QApplication

from .ui import MainWindow, STYLE


def main():
    parser = argparse.ArgumentParser(description='Dragvert — local file conversion and image tools')
    parser.add_argument('--tray', action='store_true', help='Start minimized if a system tray is available')
    parser.add_argument('files', nargs='*')
    args = parser.parse_args()
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    app = QApplication(sys.argv[:1])
    app.setApplicationName('Dragvert')
    icon = QIcon.fromTheme('dragvert')
    if icon.isNull():
        icon = QIcon(str(Path(__file__).resolve().parent.parent / 'packaging' / 'dragvert.svg'))
    app.setWindowIcon(icon)
    app.setStyleSheet(STYLE)
    runtime = QStandardPaths.writableLocation(QStandardPaths.RuntimeLocation)
    server_name = os.path.join(runtime, 'dragvert.sock')
    client = QLocalSocket()
    client.connectToServer(server_name)
    if client.waitForConnected(300):
        client.write(json.dumps({'files': [os.path.abspath(p) for p in args.files], 'tray': args.tray}).encode() + b'\n')
        client.waitForBytesWritten(1000)
        client.disconnectFromServer()
        return 0
    QLocalServer.removeServer(server_name)
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.UserAccessOption)
    if not server.listen(server_name):
        print('Could not start Dragvert IPC: ' + server.errorString(), file=sys.stderr)
        return 1
    window = MainWindow()
    clients = {}

    def connected():
        while server.hasPendingConnections():
            socket = server.nextPendingConnection()
            clients[socket] = bytearray()

            def read(socket=socket):
                clients[socket].extend(bytes(socket.readAll()))
                if len(clients[socket]) > 1024 * 1024:
                    socket.abort()
                    return
                if b'\n' not in clients[socket]:
                    return
                try:
                    data = json.loads(bytes(clients[socket]).split(b'\n')[0])
                    files = data.get('files', [])
                    if not isinstance(files, list) or not all(isinstance(p, str) for p in files):
                        return
                    if files:
                        window.set_paths(files)
                        window.showNormal()
                        window.open_wheel()
                    elif not data.get('tray'):
                        window.showNormal()
                except (ValueError, TypeError, AttributeError):
                    pass
                socket.disconnectFromServer()

            socket.readyRead.connect(read)
            socket.disconnected.connect(lambda socket=socket: (clients.pop(socket, None), socket.deleteLater()))
            if socket.bytesAvailable():
                read()

    server.newConnection.connect(connected)
    if args.files:
        window.set_paths(args.files)
        window.show()
        QTimer.singleShot(100, window.open_wheel)
    elif not args.tray or not window.tray:
        window.show()
    app.aboutToQuit.connect(window.monitor.close)
    result = app.exec_()
    server.close()
    return result


if __name__ == '__main__':
    sys.exit(main())
