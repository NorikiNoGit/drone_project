import subprocess
import os
import multiprocessing

def create_venv(venv_path, requirements_path):
    # Creating virtual environment
    subprocess.run(f"python3 -m venv {venv_path}", shell=True, check=True)
    
    # Installing dependencies from requirements.txt
    pip_install = f"{venv_path}/bin/pip install -r {requirements_path}"
    # subprocess.run(pip_install, shell=True, check=True)
    result = subprocess.run(pip_install, shell=True, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print(result.stdout.decode())
    print(result.stderr.decode())


def run_script(venv_path, script_path, requirements_path, args=None):
    # Check if virtual environment exists, if not, create it
    if not os.path.exists(venv_path):
        create_venv(venv_path, requirements_path)
    
    # Activating the virtual environment
    activate_venv = f"source {venv_path}/bin/activate"
    
    # Creating the command to execute the script
    command = f"{activate_venv} && python {script_path}"
    if args:
        command += " " + " ".join(args)
    
    # Executing the command
    process = subprocess.Popen(command, shell=True, executable="/bin/bash")
    # process.wait()
    
def worker(venv_path, script_path, requirements_path, args=None):
    run_script(venv_path, script_path, requirements_path, args)

if __name__ == "__main__":
    # Paths to the virtual environments, scripts, and requirements files
    venv1_path = "./yolov5/venv1"
    venv2_path = "./loop/venv2"
    venv3_path = "./stream_to_yolo/venv3"
    detect_script_path = "./yolov5/detect.py"
    loop_script_path = "./loop/loop.py"
    drone_script_path = "./stream_to_yolo/main.py"
    requirements1_path = "./yolov5/requirements.txt"
    requirements2_path = "./loop/requirements.txt"
    requirements3_path = "./stream_to_yolo/requirements.txt"
    
    
    
    # Arguments to pass to detect.py
    detect_args = ["--source", "0", "--nosave"]  # Add your arguments here
    
    # Creating processes
    p1 = multiprocessing.Process(target=worker, args=(venv1_path, detect_script_path, requirements1_path, detect_args))
    # p2 = multiprocessing.Process(target=worker, args=(venv2_path, loop_script_path, requirements2_path))
    p3 = multiprocessing.Process(target=worker, args=(venv3_path, drone_script_path, requirements3_path))
    
    p1.daemon = True
    # p2.daemon = True
    p3.daemon = True

    # Starting processes
    p1.start()
    # p2.start()
    p3.start()

    
    # Waiting for processes to finish
    # p1.join()
    # p2.join()
    # p3.join()
    while True:
        pass
