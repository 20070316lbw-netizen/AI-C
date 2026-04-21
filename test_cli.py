import subprocess

process = subprocess.Popen(['python3', '-m', 'aic'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
stdout, stderr = process.communicate(input="/help\n/exit\n")
print("STDOUT:", stdout)
print("STDERR:", stderr)
