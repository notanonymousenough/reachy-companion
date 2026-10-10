import unittest
import socket
from unittest.mock import patch
from reachy_companion.autonomous.header_observer import compile_filter,evaluate,metadata,vectors,receive_header,open_capture


class FilterTests(unittest.TestCase):
    def test_kernel_program_reject_vectors_and_return_exact_header_length(self):
        client,server,port,accepted,rejected=vectors();code=compile_filter(client,server,port)
        for name,packet in accepted.items():
            self.assertEqual(evaluate(code,packet),42,name)
            view=metadata(packet[:42],client,server,port)
            self.assertEqual(view['captured_header_bytes'],42)
            self.assertNotIn('payload',str(view));self.assertNotIn('checksum',view)
        for name,packet in rejected.items():self.assertEqual(evaluate(code,packet),0,name)
        for length in range(42):self.assertEqual(evaluate(code,accepted['forward'][:length]),0)
        self.assertEqual({row[3] for row in code if row[0]==0x06},{0,42})
    def test_receive_cannot_hide_kernel_payload_truncation(self):
        class BrokenKernel:
            def recvmsg_into(self,buffers,ancillary,flags):
                self.buffer_length=len(buffers[0]);self.flags=flags
                return 200,[],socket.MSG_TRUNC,()
        sock=BrokenKernel()
        with self.assertRaises(RuntimeError):receive_header(sock)
        self.assertEqual(sock.buffer_length,42);self.assertEqual(sock.flags,socket.MSG_TRUNC)

    def test_filter_install_failure_closes_protocol_zero_socket_without_binding(self):
        events=[]
        class Raw:
            def close(self):events.append('close')
            def bind(self,address):events.append('bind')
        def create(family,kind,protocol):events.append(('create',protocol));return Raw()
        with patch('reachy_companion.autonomous.header_observer.sys.platform','linux'), \
             patch('reachy_companion.autonomous.header_observer.socket.AF_PACKET',17,create=True), \
             patch('reachy_companion.autonomous.header_observer.socket.socket',side_effect=create), \
             patch('reachy_companion.autonomous.header_observer.attach',side_effect=OSError('filter unavailable')):
            with self.assertRaises(OSError):open_capture('lo',compile_filter('198.18.0.1','198.18.0.2',8781),synthetic=True)
        self.assertEqual(events,[('create',0),'close'])

    def test_flow_scope_validation(self):
        for client,server,port in [('198.18.0.1','198.18.0.1',8781),('::1','198.18.0.1',8781),('198.18.0.1','198.18.0.2',0)]:
            with self.assertRaises(ValueError):compile_filter(client,server,port)
