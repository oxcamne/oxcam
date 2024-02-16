import smtplib
from email.message import EmailMessage
import urllib.parse # To encode the email address
import hmac # To generate the signature
import time # To get the current timestamp

# Create an email message object
msg = EmailMessage()

# Set the email headers
msg['Subject'] = 'Subject of the email'
msg['From'] = 'sender@example.com'
msg['To'] = 'receiver@example.com'

# Set the email body
msg.set_content('Body of the email')

# Add the file attachment
# Replace 'path/to/file' with the actual file path
with open('path/to/file', 'rb') as f:
    file_data = f.read()
    file_name = f.name
msg.add_attachment(file_data, maintype='application', subtype='octet-stream', filename=file_name)

# Generate a one-click unsubscribe link
# Replace 'yourserver.com' with the actual server domain
# Replace 'secretkey' with a random string that only you know
base_url = 'http://yourserver.com/unsubscribe/'
email = msg['To']
encoded_email = urllib.parse.quote(email) # URL-encode the email address
expiration = int(time.time()) + 86400 # Set the expiration to 24 hours from now
signature = hmac.new(b'secretkey', (email + str(expiration)).encode(), 'sha1').hexdigest() # Generate a signature using HMAC-SHA1
unsubscribe_url = base_url + encoded_email + '/' + str(expiration) + '/' + signature # Concatenate the components

# Add the unsubscribe link to the email footer
msg.add_alternative(f"""\
<html>
  <body>
    <p>Body of the email</p>
    <p><a href="{unsubscribe_url}">Click here to unsubscribe</a></p>
  </body>
</html>
""", subtype='html')

# Add the List-Unsubscribe and List-Unsubscribe-Post headers
# Replace 'yourserver.com' with the actual server domain
# Replace 'secretkey' with a random string that only you know
msg['List-Unsubscribe'] = f'<mailto:listrequest@example.com?subject=unsubscribe>, <http://yourserver.com/unsubscribe/{encoded_email}/{expiration}/{signature}>'
msg['List-Unsubscribe-Post'] = 'List-Unsubscribe=One-Click'

# Connect to the SMTP server and send the email
# Replace 'smtp.example.com' with the actual SMTP server
# Replace 587 with the actual port number
# Replace 'username' and 'password' with the actual credentials
with smtplib.SMTP('smtp.example.com', 587) as s:
    s.starttls() # Start TLS encryption
    s.login('username', 'password') # Login to the server
    s.send_message(msg) # Send the email
