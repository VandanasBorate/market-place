from flask import Flask, request, jsonify, render_template
import paramiko
from paramiko import RSAKey
import requests
import urllib3

app = Flask(__name__)

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
    return render_template('market_place.html')  # Render the file upload form (GET request)

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
        inprox02_usage = get_disk_usage(hostname_inprox02, username, private_key_path)

        if isinstance(inprox_usage, int) and isinstance(inprox02_usage, int):
            if file_name.endswith('.iso') or file_name.endswith('.img'):
                if inprox_usage < 50:
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


node_name = 'innprox-02'
@app.route('/create_vm', methods=['GET', 'POST'])
def create_vm():
    # Define the get_available_vmid function
    #     # Define the Proxmox API details
    PROXMOX_URL = "https://192.168.1.252:8006/api2/json"
    TOKEN_ID = "pythonapi@pam!apipython"
    TOKEN_SECRET = "8b13892c-c6e9-43c0-b128-3f17dd0f932a"
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
                vmid = 200
                while vmid in existing_vmids:
                    vmid += 1
                return vmid
            else:
                raise Exception("Failed to fetch existing VMs.")
        except requests.RequestException as e:
            raise Exception(f"Error fetching VM list from Proxmox: {str(e)}")

    # Get the file_name parameter from the query string (for both GET and POST requests)
    file_name = request.args.get('file_name')
    print(file_name)
      # Fetch the file name from the URL
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
        print(url)

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
    app.run(debug=True, port=5001) 









































# @app.route('/create_vm', methods=['GET', 'POST'])
# def create_vm():
#     # Define the Proxmox API details
#     PROXMOX_URL = "https://192.168.1.252:8006/api2/json"
#     TOKEN_ID = "pythonapi@pam!apipython"
#     TOKEN_SECRET = "8b13892c-c6e9-43c0-b128-3f17dd0f932a"
#     headers = {
#         'Authorization': f'PVEAPIToken={TOKEN_ID}={TOKEN_SECRET}',
#         'Content-Type': 'application/json'
#     }

#     # Define the get_available_vmid function
#     def get_available_vmid(node):
#         url = f"{PROXMOX_URL}/nodes/{node}/qemu"
#         try:
#             response = requests.get(url, headers=headers, verify=False)
#             if response.status_code == 200:
#                 existing_vms = response.json()['data']
#                 existing_vmids = [vm['vmid'] for vm in existing_vms]
#                 vmid = 200
#                 while vmid in existing_vmids:
#                     vmid += 1
#                 return vmid
#             else:
#                 raise Exception("Failed to fetch existing VMs.")
#         except requests.RequestException as e:
#             raise Exception(f"Error fetching VM list from Proxmox: {str(e)}")

#     vmid = None  # Initialize vmid here

#     # Get the file_name parameter from the query string
#     file_name = request.args.get('file_name')  # Fetch the file name from the URL

#     if request.method == 'POST':
#         # Handle POST request for creating a VM
#         name = request.form['name']  # VM name
#         node = "innprox-02"  # Select Proxmox node where VM should be created

#         # Get an available VMID
#         vmid = get_available_vmid(node)
#         print(vmid)  # Get available VMID

#         # if not file_name:
#         #     return jsonify({"error": "file_name parameter is required!"})

#         # Create the clone payload with dynamic vmid
#         clone_payload = {
#             "newid": vmid,  # The ID for the new VM
#             "name": name,  # The name for the new VM
#             "full": 1,  # Perform a full clone
#             "storage": "storage1",  # Storage where the cloned disk will be created (adjust to your setup)
#         }

#         url = f"{PROXMOX_URL}/nodes/{node}/qemu/{file_name}/clone"
#         print(url)

#         try:
#             response = requests.post(url, headers=headers, json=clone_payload, verify=False)

#             if response.status_code in [200, 202]:
#                 message = "VM creation initiated successfully from the template!"  
#             else:
#                 message = f"Failed to clone VM: {response.text}"

#         except requests.RequestException as e:
#             message = f"Network issues: {str(e)}"

#         return render_template('create_vm.html', message=message, vmid=vmid)

#     # If GET request, get an available VMID and render the form
#     if not vmid:
#         node = "innprox-02"  # Same Proxmox node where VM should be created
#         vmid = get_available_vmid(node)  # Fetch VMID for GET requests

#     return render_template('create_vm.html', vmid=vmid, file_name=file_name)
 # Start the Flask application in debug mode
