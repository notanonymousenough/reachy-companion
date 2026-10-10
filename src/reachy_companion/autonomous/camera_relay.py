"""Video-only camera IPC replacement while factory motor daemon is withdrawn."""
import os
from pathlib import Path
import socket
import stat


class CameraRelay:
    def __init__(self):
        from reachy_mini.media.camera_gstreamer import Gst
        from reachy_mini.media.camera_constants import get_camera_specs_by_name
        from reachy_mini.daemon.utils import CAMERA_SOCKET_PATH
        self.Gst,self.path = Gst,Path(CAMERA_SOCKET_PATH)
        if self.path.exists():
            info=self.path.stat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid!=os.getuid(): raise RuntimeError('Unknown camera IPC owner')
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as probe:
                probe.settimeout(.3)
                try: probe.connect(str(self.path))
                except ConnectionRefusedError: pass
                else: raise RuntimeError('Another camera IPC writer is active')
            self.path.unlink()
        specs=get_camera_specs_by_name('wireless')
        width,height=specs.default_resolution.value[:2]
        if (width,height)!=(1280,720): raise RuntimeError('Unaudited wireless camera geometry')
        Gst.init([])
        # dmabuf-backed libcamerasrc buffers feed the same unixfd endpoint as
        # the factory server. No audio, WebRTC, file sink or motor imports.
        self.pipeline=Gst.parse_launch('libcamerasrc ! video/x-raw,width=1280,height=720,framerate=30/1,format=YUY2,colorimetry=bt709,interlace-mode=progressive '
            '! queue max-size-buffers=2 leaky=downstream ! videorate drop-only=true max-rate=5 '
            '! unixfdsink socket-path='+str(self.path)+' sync=false')
        if self.pipeline.set_state(Gst.State.PLAYING)==Gst.StateChangeReturn.FAILURE:
            self.close();raise RuntimeError('Video-only relay failed')
        _,state,_=self.pipeline.get_state(2*Gst.SECOND)
        if state!=Gst.State.PLAYING:
            self.close();raise RuntimeError('Video-only relay did not become ready')
    def close(self):
        self.pipeline.set_state(self.Gst.State.NULL)
        _,state,_=self.pipeline.get_state(2*self.Gst.SECOND)
        if state!=self.Gst.State.NULL:raise RuntimeError('Video-only relay shutdown unknown')
        self.path.unlink(missing_ok=True)
