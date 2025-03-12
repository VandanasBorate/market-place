from flask import Flask, request, jsonify, render_template
import paramiko
from paramiko import RSAKey
import datetime
import re
import requests
import os

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

    
    stripped_step = step.strip()
    if re.match(r'^\x1b\[25h$', stripped_step) or re.match(r'^\[25h$', stripped_step):
        return None  # Skip this row entirely

    
    if '\x1b[25l' in step:
        # Split the string around [25l and join back without it
        step_parts = step.split('\x1b[25l')
        step = ''.join(step_parts)
    
    if '\x1b[25h' in step:
        # Split the string around [25l and join back without it
        step_parts = step.split('\x1b[25h')
        step = ''.join(step_parts)
    # Clean leading/trailing spaces after cleaning
    return step.strip() if step.strip() else None  # Return None if the cleaned step is empty



# Function to get disk usage from a Proxmox node
def get_disk_usage(hostname, username, private_key_path):
    try:
        # Create an SSH client instance
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Load the private key for authentication
        private_key = RSAKey.from_private_key_file(private_key_path)

        # Connect to the Proxmox node
        ssh_client.connect(hostname, username=username, pkey=private_key, port=22)

        # Run the `df` command to check disk usage
        stdin, stdout, stderr = ssh_client.exec_command("df -h --output=source,pcent /var/lib/vz | tail -n 1")
        output = stdout.read().decode().strip()

        # Extract percentage of usage from the output (e.g., '70%' from '/var/lib/vz')
        used_percentage = int(output.split()[1].replace('%', ''))
        ssh_client.close()

        return used_percentage
    except Exception as e:
        return {"message": f"Failed to check disk usage: {str(e)}"}

# Function to upload a file to Proxmox
def upload_file_to_proxmox(local_file, remote_file, hostname, port, username, private_key_path, node_name):
    try:
        # Create an SSH client instance
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Load the private key for authentication
        private_key = RSAKey.from_private_key_file(private_key_path)

        # Connect to the Proxmox node
        ssh_client.connect(hostname, port=port, username=username, pkey=private_key)

        # Open an SFTP session to check if the file exists
        sftp_client = ssh_client.open_sftp()

        try:
            # Check if the file already exists on the remote server
            sftp_client.stat(remote_file)
            sftp_client.close()
            ssh_client.close()
            return {'message': f"File {remote_file} already exists on {node_name}. No upload needed."}
        except FileNotFoundError:
            # If the file does not exist, proceed with the upload
            sftp_client.put(local_file, remote_file)
            sftp_client.close()
            ssh_client.close()

            return {'status': 'success', 'message': f"File {local_file} uploaded to Proxmox node {node_name} at {remote_file}"}
    
    except Exception as e:
        return {'message': f"Connection failed: {str(e)}"}


@app.route('/')
def home():
    return render_template('marketplace.html')


# Define the /upload_file route to handle both POST and GET requests
@app.route('/upload_file', methods=['POST'])
def handle_upload():
    if request.method == 'POST':
        data = request.get_json()
        file_name = data.get('file')
        
        local_file_path = f"/home/nfs_client/{file_name}"  # Adjust path as per your environment

        # Define your Proxmox node details for SSH connection
        hostname_inprox = '192.168.1.107'  # Proxmox node 1 IP (inprox)
        hostname_inprox02 = '192.168.1.252'  # Proxmox node 2 IP (inprox02)
        username = 'root'  # Proxmox username
        private_key_path = '/home/innuser002/.ssh/id_rsa'  # Path to your private SSH key

        # Get disk usage for both nodes
        inprox_usage = get_disk_usage(hostname_inprox, username, private_key_path)
        print(inprox_usage)
        inprox02_usage = get_disk_usage(hostname_inprox02, username, private_key_path)
        print(inprox02_usage)
        

        if isinstance(inprox_usage, int) and isinstance(inprox02_usage, int):
            if file_name.endswith('.iso') or file_name.endswith('.img'):
                if inprox_usage < 90:
                    result = upload_file_to_proxmox(local_file_path, f"/var/lib/vz/template/iso/{file_name}", hostname_inprox, 22, username, private_key_path, "innprox")
                elif inprox02_usage < 95:
                    result = upload_file_to_proxmox(local_file_path, f"/var/lib/vz/template/iso/{file_name}", hostname_inprox02, 22, username, private_key_path, "innprox-02")
                else:
                  result = {'message': "Both storage locations are over 95% full. Cannot upload file."}
            else:
                return render_template("create_vm.html")
            
        else:
            result = {'message': "Failed to check disk usage on both Proxmox nodes."}
        
        return jsonify(result)


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
                return render_template('create_lxc.html', ct_id=result, file_name=file_name, logs=logs)

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

        # # Validate input fields
        # if not vmid or not name or not password or not ssh_key:
        #     return render_template('create_lxc.html', error="All fields must be filled out!")

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
            print(command)
            stdin, stdout, stderr = ssh_client.exec_command(command)
          
            # Capture the output and errors in real-time
            while True:
                # Read line by line from stdout
                line = stdout.readline().strip()
                if line == '' and stdout.channel.exit_status_ready():
                    break
                if line:
                    cleaned_step = clean_step(line)
                    if cleaned_step:
                        logs.append(f"{get_timestamp()} - {cleaned_step}")

            # Capture error output if any
            error = stderr.read().decode().strip()
            if error:
                return render_template('create_lxc.html', error=f"Error occurred: {error}", logs=logs)

            # After container creation, fetch the IP and MAC address
            ip_command = f"pct exec {vmid} -- ip -4 a show eth0 | grep inet | awk '{{print $2}}' | cut -d'/' -f1"
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

            # Debugging output
            print(f"IP Address: {ip_address}")
            print(f"MAC Address: {mac_address}")
            print(f"Logs: {logs}")

            # return render_template('create_lxc.html', success_message="LXC Container created successfully!",
                                #   ip_address=ip_address, mac_address=mac_address, logs=logs)
            return render_template('logfile.html', 
                       success_message="LXC Container created successfully!",
                       ip_address=ip_address, 
                       mac_address=mac_address, 
                       logs=logs,
                       name=name,
                       vmid=vmid,
                       ssh_key=ssh_key)


        except Exception as e:
            return render_template('create_lxc.html', error=f"Error connecting to Proxmox: {str(e)}", logs=logs)

        finally:
            # Ensure the SSH client is closed to release resources
            ssh_client.close()

    return render_template('create_lxc.html', logs=logs)




# Define the route for creating a VM
@app.route('/create_vm', methods=['GET', 'POST'])
def create_vm():
    # Define the get_available_vmid function
    PROXMOX_URL = "https://192.168.1.252:8006/api2/json"
    TOKEN_ID = "pythonapi@pam!apipython"
    TOKEN_SECRET = "8b13892c-c6e9-43c0-b128-3f17dd0f932a"
    node_name  = "innprox-02"
    headers = {
        'Authorization': f'PVEAPIToken={TOKEN_ID}={TOKEN_SECRET}',
        'Content-Type': 'application/json'
    }

    def get_available_vmid(node):
        url = f"{PROXMOX_URL}/nodes/{node}/qemu"
        try:
            response = requests.get(url, headers=headers, verify=False)
            if response.status_code == 200:
                existing_vms = response.json()['data']
                existing_vmids = [vm['vmid'] for vm in existing_vms]
                vmid = 2008
                while vmid in existing_vmids:
                    vmid += 1
                return vmid
            else:
                raise Exception("Failed to fetch existing VMs.")
        except requests.RequestException as e:
            raise Exception(f"Error fetching VM list from Proxmox: {str(e)}")

    # Get the file_name parameter from the query string (for both GET and POST requests)
    file_name = request.args.get('file_name')
    print(f"Requested file: {file_name}")

    # Check if the file exists at the specified location
    file_path = f"/home/nfs_client/{file_name}"
    if not os.path.exists(file_path):
        message = f"File '{file_name}' does not exist at the specified location."
        return render_template('create_vm.html', message=message)

    # Proceed with the VM creation if file exists
    vmid = get_available_vmid(node_name)  # Fetch VMID once for both GET and POST requests

    if request.method == 'POST':
        # Handle POST request for creating a VM
        name = request.form['name']  # VM name
        
        # Create the clone payload with dynamic vmid
        clone_payload = {
            "newid": vmid,  # The ID for the new VM
            "name": name,  # The name for the new VM
            "full": 1,  # Perform a full clone
            "storage": "storage1",  # Storage where the cloned disk will be created (adjust to your setup)
        }

        url = f"{PROXMOX_URL}/nodes/{node_name}/qemu/{file_name}/clone"
        try:
            response = requests.post(url, headers=headers, json=clone_payload, verify=False)
            if response.status_code in [200, 202]:
                message = "VM creation initiated successfully from the template!"  
            else:
                message = f"Failed to clone VM: {response.text}"
        except requests.RequestException as e:
            message = f"Network issues: {str(e)}"

        return render_template('create_vm.html', message=message, vmid=vmid)

    # For GET request, render the form with vmid and file_name
    return render_template('create_vm.html', vmid=vmid, file_name=file_name)



if __name__ == '__main__':
    app.run(debug=True, port=5000)
