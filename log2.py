from flask import Flask, request, jsonify, render_template
import paramiko
from paramiko import RSAKey
import datetime
import re

app = Flask(__name__)

# Function to get the current timestamp
def get_timestamp():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# Function to clean step (removing unwanted data)
def clean_step(step):
    # Remove specific unwanted pattern [25l or other escape sequences
    unwanted_patterns = r'[\x1b\x1B]\[[0-9;]*[a-zA-Z]'  # Regex for escape sequences and [25l specifically
    step = re.sub(unwanted_patterns, '', step)

    # Optionally remove progress indicators or specific symbols (optional)
    progress_indicators = r'[\?✔️✖️⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]'
    step = re.sub(progress_indicators, '', step)

    # Remove lines that are left only with escape sequences (like [25h)
    if re.match(r'^\x1b\[25h$', step.strip()):
        return None  # Skip this row entirely
    if '\x1b[25l' in step:
        # print(f"Step with [25l: {step}")

        # Split the string around [25l and join back without it
        step_parts = step.split('\x1b[25l')
        step = ''.join(step_parts)

    # Clean leading/trailing spaces after cleaning
    return step.strip() if step.strip() else None  # Return None if the cleaned step is empty


@app.route('/')
def home():
    return render_template('marketplace.html')


@app.route('/create_lxc', methods=['GET', 'POST'])
def lxc_container():
    logs = []  # List to store logs with timestamps

    if request.method == 'GET':
        try:
            file_name = request.args.get('file_name')

            # Proxmox node SSH connection details
            hostname = '192.168.1.252'
            username = 'root'
            private_key_path = '/home/innuser002/.ssh/id_rsa'
            port = 22

            # SSH client setup
            ssh_client = paramiko.SSHClient()
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            private_key = RSAKey.from_private_key_file(private_key_path)
            ssh_client.connect(hostname, port=port, username=username, pkey=private_key)

            # Command to get the next available container ID
            stdin, stdout, stderr = ssh_client.exec_command('pvesh get /cluster/nextid')
            result = stdout.read().decode().strip()
            error = stderr.read().decode()

            if result:
                return render_template('create_lxc.html', ct_id=result, file_name=file_name,logs=logs)

            if error:
                return f"Error occurred: {error}"

        except Exception as e:
            return f"Error connecting to Proxmox: {str(e)}"

        finally:
            ssh_client.close()

    elif request.method == 'POST':
        vmid = request.form.get('vmid')
        file = request.form.get('file_name')
        name = request.form.get('name')
        password = request.form.get('pass')
        ssh_key = '"' + str(request.form.get('ssh', '')) + '"'

        # Validate input fields
        if not vmid or not name or not password or not ssh_key:
            return render_template('create_lxc.html', error="All fields must be filled out!")

        try:
            # Proxmox node SSH connection details
            hostname = '192.168.1.252'
            username = 'root'
            private_key_path = '/home/innuser002/.ssh/id_rsa'
            port = 22

            # SSH client setup
            ssh_client = paramiko.SSHClient()
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            private_key = RSAKey.from_private_key_file(private_key_path)
            ssh_client.connect(hostname, port=port, username=username, pkey=private_key)

            # Execute the container creation command
            command = f'/bin/bash {file} {vmid} {name} {password} {ssh_key}'
            stdin, stdout, stderr = ssh_client.exec_command(command)

            # Capture the output and errors
            result = stdout.read().decode().strip()
            error = stderr.read().decode().strip()

            if error:
                return render_template('create_lxc.html', error=f"Error occurred: {error}")

            if result:
                # Split result into individual lines (each line represents a step)
                result_steps = result.splitlines()
                for step in result_steps:
                    cleaned_step = clean_step(step)

                    if cleaned_step:
                        logs.append(f"{get_timestamp()} - {cleaned_step}")

                # Command to fetch the IPv4 address of eth0
                ip_command = f"pct exec {vmid} -- ip -4 a show eth0 | grep inet | awk '{{print $2}}' | cut -d'/' -f1"
                # Command to fetch the full MAC address
                mac_command = f"pct exec {vmid} -- ip link show eth0 | grep link/ether | awk '{{print $2}}'"

                # Execute the command for IP address
                stdin, stdout, stderr = ssh_client.exec_command(ip_command)
                ip_result = stdout.read().decode().strip()

                # Execute the command for MAC address
                stdin, stdout, stderr = ssh_client.exec_command(mac_command)
                mac_result = stdout.read().decode().strip()

                # Handle the case where results might be empty or not found
                ip_address = ip_result if ip_result else "N/A"
                mac_address = mac_result if mac_result else "N/A"

                # Log the IP and MAC address
                logs.append(f"{get_timestamp()} - IP Address: {ip_address}")
                logs.append(f"{get_timestamp()} - MAC Address: {mac_address}")

                  # Debugging output
                print(f"IP Address: {ip_address}")
                print(f"MAC Address: {mac_address}")
                print(f"Logs: {logs}")

                return render_template('create_lxc.html', success_message="LXC Container created successfully!",
                                      ip_address=ip_address, mac_address=mac_address, logs=logs)

        except Exception as e:
            return render_template('create_lxc.html', error=f"Error connecting to Proxmox: {str(e)}",logs=logs)

        finally:
            # Ensure the SSH client is closed to release resources
            ssh_client.close()

    return render_template('create_lxc.html', logs=logs)


if __name__ == '__main__':
    app.run(debug=True, port=5000)
