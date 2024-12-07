from flask import Flask, render_template, request
import requests
import urllib3

# Disable SSL warnings for testing purposes. This prevents warnings when using self-signed SSL certificates.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Initialize the Flask app.
app = Flask(__name__)
app.secret_key = '\x1f\xf9K\x91E1\x7fJ\x94\xd8\xea\x1d\xe5r\xb9\xe1=p\xe5\xf8\n\xca\x88\x89'  # Secret key used for session management in Flask.

# Proxmox server details for API access.
PROXMOX_URL = "https://192.168.1.252:8006/api2/json"  # URL for Proxmox API endpoint.
TOKEN_ID = "pythonapi@pam!apipython"  # Token ID for authentication.
TOKEN_SECRET = "8b13892c-c6e9-43c0-b128-3f17dd0f932a"  # Token secret for authentication.
node = "innprox-02"  # Node on which the VM will be created.

# API headers to include authorization and content type.
headers = {
    'Authorization': f'PVEAPIToken={TOKEN_ID}={TOKEN_SECRET}',  # Authorization header for Proxmox API token.
    'Content-Type': 'application/json'  # Specify JSON content type for the request body.
}


# Function to get the next available VM ID
def get_available_vmid(node):
    url = f"{PROXMOX_URL}/nodes/{node}/qemu"
    print(url)
    try:
        response = requests.get(url, headers=headers, verify=False)
        if response.status_code == 200:
            existing_vms = response.json()['data']
            existing_vmids = [vm['vmid'] for vm in existing_vms]
            # Find the first available VMID (greater than 100 and not already in use)
            vmid = 200
            while vmid in existing_vmids:
                vmid += 1
            return vmid
        else:
            raise Exception("Failed to fetch existing VMs.")
    except requests.RequestException as e:
        raise Exception(f"Error fetching VM list from Proxmox: {str(e)}")

@app.route('/')
def index():
    # Get the available node and generate a new VMID for the user
    # Get the available node
    vmid = get_available_vmid(node)  # Get the available VMID for that node
    
    # Pass the vmid to the template
    return render_template('create_vm.html', vmid=vmid)

@app.route('/create_vm', methods=['POST'])
def create_vm():
    # Get data from the form submitted by the user.
    # Automatically select an available node and generate the VMID
      # Get the available node
    vmid = get_available_vmid(node)  # VM ID from the form input.
    name = request.form['name'] 
    template_id = 179                  # Template ID (ensure it’s correct)

    clone_payload = {
        "newid": vmid,  # The ID for the new VM.
        "name": name,  # The name for the new VM.
        "full": 1,  # Perform a full clone (copy the entire template including the disk).
        "storage": "storage1",  # Storage where the cloned disk will be created (adjust according to your setup).
    }

    # Proxmox API endpoint for cloning the template.
    url = f"{PROXMOX_URL}/nodes/{node}/qemu/{template_id}/clone"

    try:
        # Make a POST request to Proxmox API to clone the template into a new VM with the provided configuration.
        response = requests.post(url, headers=headers, json=clone_payload, verify=False)

        # Log API response for debugging
        print("API Response Status Code:", response.status_code)
        print("API Response Text:", response.text)

        # Check if the request was successful (HTTP status codes 200 or 202).
        if response.status_code in [200, 202]:
            message = "VM creation initiated successfully from the template!"  # Success message.
            print("VM creation initiated successfully:", response.json())  # Log the successful response for debugging.

            # Check the response content to get the VM ID and other details
           

        else:
            # If the request failed (e.g., due to a missing template or other issues), show this error message.
            message = f"Failed to clone VM: {response.text}"

    except requests.RequestException as e:
        # Handle any exceptions that occur during the API request (e.g., network issues).
        message = f"Network issues: {str(e)}"

    # Render the 'create_vm.html' template, passing the message to display the result.
    return render_template('/create_vm.html', message=message)


    

if __name__ == "__main__":
    app.run(debug=True)
