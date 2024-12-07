from flask import Flask, request, jsonify, render_template
import paramiko
from paramiko import RSAKey
import os
import create_vm_template

app = Flask(__name__)

def get_disk_usage(hostname, username, private_key_path):
    """Check the disk usage of the Proxmox server."""
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

        # Extract percentage of usage from the output (e.g., '70%' from '/var/lib/vz)
        used_percentage = int(output.split()[1].replace('%', ''))
        print(used_percentage)
        
        ssh_client.close()
        
        return used_percentage
    except Exception as e:
        return {"message": f"Failed to check disk usage:"}

def upload_file_to_proxmox(local_file, remote_file, hostname, port, username, private_key_path, node_name):
    try:
        # Create an SSH client instance
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Explicitly load the RSA key
        private_key = RSAKey.from_private_key_file(private_key_path)

        # Use private key for SSH authentication
        ssh_client.connect(
            hostname,
            port=port,
            username=username,
            pkey=private_key,  # Use the loaded RSA key
            allow_agent=False,
            look_for_keys=False
        )

        # Open an SFTP session to check if the file exists
        sftp_client = ssh_client.open_sftp()

        try:
            # Check if the file already exists on the remote server
            sftp_client.stat(remote_file)  # If this succeeds, the file exists
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
        return { 'message': f"connection failed"}

@app.route('/')
def home():
    return render_template('market_place.html')  # Renders HTML form for file upload

@app.route('/upload_file', methods=['POST'])
def handle_upload():
    data = request.get_json()
    file_name = data.get('file')
    
    # Define local file path (adjust according to your actual path)
    local_file_path = f"/home/nfs_client/{file_name}"  # Adjust path as per your environment
    
    # Check the file extension to determine the correct remote path
    if file_name.endswith('.iso') or file_name.endswith('.img'):
        remote_file_path = f"/var/lib/vz/template/iso/{file_name}"  # For ISO and IMG files
    else:
        # remote_file_path = f"/var/lib/vz/images/{file_name}"  # For other file types
        create_vm_template.get_available_vmid(file_name)  # Call the function
         
    
    # Set Proxmox connection details
    hostname_inprox = '192.168.1.107'  # Proxmox node 1 IP (inprox)
    hostname_inprox02 = '192.168.1.252'  # Proxmox node 2 IP (inprox02)
    username = 'root'  # Proxmox username
    private_key_path = '/home/innuser002/.ssh/id_rsa'  # Path to your private SSH key

    # Check disk usage on both nodes
    inprox_usage = get_disk_usage(hostname_inprox, username, private_key_path)
    inprox02_usage = get_disk_usage(hostname_inprox02, username, private_key_path)

    if isinstance(inprox_usage, int) and isinstance(inprox02_usage, int):
       
        if inprox_usage < 50:
            result = upload_file_to_proxmox(local_file_path, remote_file_path, hostname_inprox, 22, username, private_key_path, "innprox")
        
        elif inprox02_usage < 95:
            result = upload_file_to_proxmox(local_file_path, remote_file_path, hostname_inprox02, 22, username, private_key_path, "innprox-02")
        else:
            # If both storages are full, return an error
            result = { 'message': "Both storage locations are over 95% full. Cannot upload file."}
    else:
        result = { 'message': "Failed to check disk usage on both Proxmox nodes."}
    
    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True)  # Start the Flask application in debug mode
