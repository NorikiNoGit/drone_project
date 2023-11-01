import logging
import contextlib
import os
import socket
import subprocess
import threading
import time
import requests
import re

import cv2 as cv
import numpy as np

from droneapp.models.base import Singleton


logger = logging.getLogger(__name__)

DEFAULT_DISTANCE = 0.30
DEFAULT_SPEED = 10
DEFAULT_DEGREE = 10

FRAME_X = int(960/3)
FRAME_Y = int(720/3)
FRAME_AREA = FRAME_X * FRAME_Y

FRAME_SIZE = FRAME_AREA * 3
FRAME_CENTER_X = FRAME_X / 2
FRAME_CENTER_Y = FRAME_Y / 2

CMD_FFMPEG = (f'ffmpeg -hwaccel auto -hwaccel_device opencl -i pipe:0 '
              f'-pix_fmt bgr24 -s {FRAME_X}x{FRAME_Y} -f rawvideo pipe:1')


class DroneManager(metaclass=Singleton):
    def __init__(self, host_ip='192.168.10.2', host_port=8889,
                 drone_ip='192.168.10.1', drone_port=8889,
                 is_imperial=False, speed=DEFAULT_SPEED):
        self.host_ip = host_ip
        self.host_port = host_port
        self.drone_ip = drone_ip
        self.drone_port = drone_port
        self.drone_address = (drone_ip, drone_port)
        self.is_imperial = is_imperial
        self.speed = speed
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((self.host_ip, self.host_port))

        self.response = None
        self.stop_event = threading.Event()
        self._response_thread = threading.Thread(target=self.receive_response,
                                           args=(self.stop_event, ))
        self._response_thread.start()

        # yoloで検出した結果をここに入れる。
        self.detected_results = {}
        self._recieve_detected_results = threading.Thread(target=self.receive_video_results, 
                                                          args=(self.stop_event,))
        self._recieve_detected_results.start()

        # commandを重複して実行しないようにする。
        self._command_semaphore = threading.Semaphore(1)
        self._command_thread = None

        self.patrol_event = None
        self.is_patrol = False
        self._patrol_semaphore = threading.Semaphore(1)
        self._thread_patrol = None

        self.proc = subprocess.Popen(CMD_FFMPEG.split(' '),
                                     stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE)
        self.proc_stdin = self.proc.stdin
        self.proc_stdout = self.proc.stdout

        self.video_port = 11111

        self._receive_video_thread = threading.Thread(
            target=self.receive_video,
            args=(self.stop_event, self.proc_stdin,
                  self.host_ip, self.video_port,))
        self._receive_video_thread.start()

        self.send_command('command')
        self.send_command('streamon')
        self.set_speed(self.speed)

    def receive_response(self, stop_event):
        while not stop_event.is_set():
            try:
                self.response, ip = self.socket.recvfrom(3000)
                logger.info({'action': 'receive_response',
                             'response': self.response})
            except socket.error as ex:
                logger.error({'action': 'receive_response',
                             'ex': ex})
                break

    def __dell__(self):
        self.stop()

    def stop(self):
        self.stop_event.set()
        retry = 0
        while self._response_thread.isAlive():
            time.sleep(0.3)
            if retry > 30:
                break
            retry += 1
        self.socket.close()
        os.kill(self.proc.pid, 9)
        # Windows
        # import signal
        # os.kill(self.proc.pid, signal.CTRL_C_EVENT)

    def send_command(self, command, blocking=True):
        self._command_thread = threading.Thread(
            target=self._send_command,
            args=(command, blocking,))
        self._command_thread.start()

    def _send_command(self, command, blocking=True):
        is_acquire = self._command_semaphore.acquire(blocking=blocking)
        if is_acquire:
            with contextlib.ExitStack() as stack:
                stack.callback(self._command_semaphore.release)
                logger.info({'action': 'send_command', 'command': command})
                self.socket.sendto(command.encode('utf-8'), self.drone_address)

                retry = 0
                while self.response is None:
                    time.sleep(0.3)
                    if retry > 3:
                        break
                    retry += 1

                if self.response is None:
                    response = None
                else:
                    response = self.response.decode('utf-8')
                self.response = None
                return response

        else:
            logger.warning({'action': 'send_command', 'command': command, 'status': 'not_acquire'})

    def takeoff(self):
        return self.send_command('takeoff')

    def land(self):
        return self.send_command('land')

    def move(self, direction, distance):
        distance = float(distance)
        if self.is_imperial:
            distance = int(round(distance * 30.48))
        else:
            distance = int(round(distance * 100))
        return self.send_command(f'{direction} {distance}')

    def up(self, distance=DEFAULT_DISTANCE):
        return self.move('up', distance)

    def down(self, distance=DEFAULT_DISTANCE):
        return self.move('down', distance)

    def left(self, distance=DEFAULT_DISTANCE):
        return self.move('left', distance)

    def right(self, distance=DEFAULT_DISTANCE):
        return self.move('right', distance)

    def forward(self, distance=DEFAULT_DISTANCE):
        return self.move('forward', distance)

    def back(self, distance=DEFAULT_DISTANCE):
        return self.move('back', distance)

    def set_speed(self, speed):
        return self.send_command(f'speed {speed}')

    def clockwise(self, degree=DEFAULT_DEGREE):
        return self.send_command(f'cw {degree}')

    def counter_clockwise(self, degree=DEFAULT_DEGREE):
        return self.send_command(f'ccw {degree}')

    def flip_front(self):
        return self.send_command('flip f')

    def flip_back(self):
        return self.send_command('flip b')

    def flip_left(self):
        return self.send_command('flip l')

    def flip_right(self):
        return self.send_command('flip r')

    def patrol(self):
        if not self.is_patrol:
            self.patrol_event = threading.Event()
            self._thread_patrol = threading.Thread(
                target=self._patrol,
                args=(self._patrol_semaphore, self.patrol_event,))
            self._thread_patrol.start()
            self.is_patrol = True

    def stop_patrol(self):
        if self.is_patrol:
            self.patrol_event.set()
            retry = 0
            while self._thread_patrol.isAlive():
                time.sleep(0.3)
                if retry > 300:
                    break
                retry += 1
            self.is_patrol = False

    def _patrol(self, semaphore, stop_event):
        is_acquire = semaphore.acquire(blocking=False)
        if is_acquire:
            logger.info({'action': '_patrol', 'status': 'acquire'})
            with contextlib.ExitStack() as stack:
                stack.callback(semaphore.release)
                status = 0
                while not stop_event.is_set():
                    status += 1
                    if status == 1:
                        self.up()
                    if status == 2:
                        self.clockwise(90)
                    if status == 3:
                        self.down()
                    if status == 4:
                        status = 0
                    time.sleep(5)
        else:
            logger.warning({'action': '_patrol', 'status': 'not_acquire'})

    def receive_video_results(self, stop_event):
        # yoloからで認識された結果をapiを使って取得する。
        while not stop_event.is_set():
            try:
                results = requests.get('http://127.0.0.1:50111')
                self.detected_results = results.json()
                logger.debug({'action': 'receive_yolo_results', 'status':'success', 'detected_object': self.detected_results})
                # print(self.detected_results)
            except Exception as ex:
                logger.debug({'action': 'receive_yolo_results', 'ex': ex })
                time.sleep(1)  # Wait for 1 second before retrying
                continue
            
            

                


    def receive_video(self, stop_event, pipe_in, host_ip, video_port):
        # ドローン側が送ってくるバイナリの映像をUDPで取得するための関数
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock_video:
            sock_video.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock_video.settimeout(.5)
            sock_video.bind((host_ip, video_port))
            data = bytearray(2048)
            while not stop_event.is_set():
                try:
                    # ドローンのバイナリデータをdataという変数に格納する。dataは念の為2048byteの大きさで作ってある。
                    size, addr = sock_video.recvfrom_into(data)
                    # logger.info({'action': 'receive_video', 'data': data})
                except socket.timeout as ex:
                    logger.warning({'action': 'receive_video', 'ex': ex })
                    time.sleep(0.5)
                    continue
                except socket.error as ex:
                    logger.error({'action': 'receive_video', 'ex': ex})
                    break

                try:
                    pipe_in.write(data[:size]) # pipe_inはffmpegの入力パイプ。それに先ほど取得したdataを送信する。dataは2048byteだが送られてくるデータがそれより小さいかもしれないので、サイズ分だけ送る。
                    pipe_in.flush()
                except Exception as ex:
                    logger.error({'action': 'receive_video', 'ex': ex})
                    break

    def video_binary_generator(self):
        # ffmpegから送られてきたframeデータをopen cvに渡せる形にする関数
        while True:
            try:
                frame = self.proc_stdout.read(FRAME_SIZE)
            except Exception as ex:
                logger.error({'action': 'video_binary_generator', 'ex': ex})
                continue

            if not frame:
                continue

            frame = np.fromstring(frame, np.uint8).reshape(FRAME_Y, FRAME_X, 3)
            yield frame

    def video_jpeg_generator(self):
        # video_binary_generator()から受け取ったframeデータをweb pageで表示可能なようにjpeg binaryにしてあげる関数。server.pyにデータを渡す
        for frame in self.video_binary_generator():

            # 以下付け足しました。
            # Webカメラの映像をキャプチャする
            camera = cv.VideoCapture(0)
            success, frame = camera.read()
            _, jpeg = cv.imencode('.jpg', frame)
                 

            # _, jpeg = cv.imencode('.jpg', frame)
            jpeg_binary = jpeg.tobytes()
            

            detected_results = self.detected_results
            yolo_is_on = False
            try:
                target_is_on = False
                for detected_result in detected_results:
                    label = detected_result.get("label","")
                    coordinates = detected_result.get("coordinates", "")
                    confidence = detected_result.get("confidence","")
                    height = detected_result.get("height","")
                    width = detected_result.get("width","")
                    target = detected_result.get("target","")
                    
                    if coordinates:  # coordinatesが空でない場合
                        yolo_is_on = True
                        numbers = re.findall(r'\d+', coordinates)
                        x1, x2, y1, y2 = map(int, numbers)
                        frame_center_x = width/2
                        frame_center_y = height/2
                        if label == target:
                            target_is_on = True
                            object_center_x = (x1+x2)/2
                            object_center_y = (y1+y2)/2
                
                if target_is_on == True:
                    gap_x = frame_center_x-object_center_x
                    gap_y = frame_center_y-object_center_y
                else:
                    gap_x = 0
                    gap_y = 0
                        
            except Exception as e:
                print(e)

            if yolo_is_on == True:
                drone_x, drone_y, drone_z, speed = 0, 0, 0, self.speed
                if gap_x < -30:
                    drone_y = -30
                if gap_x > 30:
                    drone_y = 30
                if gap_y < -15:
                    drone_z = -30
                if gap_y > 15:
                    drone_z = 30
                # if percent_face > 0.30:
                #     drone_x = -30
                # if percent_face < 0.02:
                #     drone_x = 30
                # self.send_command(f'go {drone_x} {drone_y} {drone_z} {speed}',
                #                 blocking=False)
                # break
            yield jpeg_binary

            

            
                
                
                
          
