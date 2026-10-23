"""Auxiliar mínimo de PTY, iniciado por subprocess sem executar callbacks após fork."""
import fcntl
import os
import sys
import termios


def main():
    """Assume a PTY como terminal controlador da nova sessão e substitui o auxiliar."""
    try:
        fcntl.ioctl(0,termios.TIOCSCTTY,0)
        os.tcsetpgrp(0,os.getpgrp())
        os.execvpe(sys.argv[1],sys.argv[1:],os.environ)
    except BaseException as exc:
        os.write(2,(str(exc)+'\r\n').encode('utf-8','replace'))
        return 127


if __name__=='__main__':raise SystemExit(main())
