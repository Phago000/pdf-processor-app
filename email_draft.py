import streamlit as st
import base64
import json
import socket
import time
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import pandas as pd
from datetime import datetime

# Define scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.compose']

def get_gmail_service(max_retries=3):
    """Initialize Gmail service with OAuth2 and retry logic"""
    for attempt in range(max_retries):
        try:
            creds = None
            
            if 'gmail_token' in st.session_state:
                creds = Credentials.from_authorized_user_info(
                    json.loads(st.session_state['gmail_token']), 
                    SCOPES
                )
            
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(Request())
                    except Exception as e:
                        st.warning("Token refresh failed, attempting reauthorization...")
                        creds = None
                
                if not creds:
                    try:
                        client_config = {
                            "installed": {
                                "client_id": st.secrets["gmail_credentials"]["client_id"],
                                "client_secret": st.secrets["gmail_credentials"]["client_secret"],
                                "project_id": st.secrets["gmail_credentials"]["project_id"],
                                "auth_uri": st.secrets["gmail_credentials"]["auth_uri"],
                                "token_uri": st.secrets["gmail_credentials"]["token_uri"],
                                "auth_provider_x509_cert_url": st.secrets["gmail_credentials"]["auth_provider_x509_cert_url"],
                                "redirect_uris": ["http://localhost:8502"]
                            }
                        }
                        
                        flow = InstalledAppFlow.from_client_config(
                            client_config, 
                            SCOPES,
                            redirect_uri='http://localhost:8502'
                        )
                        
                        try:
                            port_number = 8502
                            creds = flow.run_local_server(
                                port=port_number,
                                access_type='offline',
                                prompt='consent'
                            )
                            # Save the credentials for future use
                            st.session_state['gmail_token'] = creds.to_json()
                            
                        except socket.error:
                            st.error(f"Port {port_number} is in use. Please try again in a few minutes.")
                            return None
                            
                    except Exception as e:
                        st.error(f"Authentication failed: {str(e)}")
                        if attempt < max_retries - 1:
                            time.sleep(2)
                            continue
                        return None
            
            service = build('gmail', 'v1', credentials=creds)
            # Test the connection
            service.users().getProfile(userId='me').execute()
            return service
            
        except Exception as e:
            if attempt < max_retries - 1:
                st.warning(f"Attempt {attempt + 1} failed, retrying...")
                time.sleep(2)
                continue
            st.error(f"Failed to initialize Gmail service after {max_retries} attempts: {str(e)}")
            return None

def create_settlement_template(currency, value):
    """Create settlement email template with proper formatting"""
    subject = f"Settlement of Subscription"
    
    # Format the value with commas for thousands
    formatted_value = "{:,.2f}".format(float(value))
    
    # Plain text version
    body = f"""Dear Sirs,

We have settled {currency} {formatted_value} for the subscription.

Enclosed is the payment reference and order information for your kind reference.

Should you have any questions, please feel free to contact us."""

    # HTML version with the exact signature
    html_body = f"""
    <div style="font-family: Tahoma, sans-serif;">
        <p>Dear Sirs,</p>
        <p>We have settled {currency} {formatted_value} for the subscription.</p>
        <p>Enclosed is the payment reference and order information for your kind reference.</p>
        <p>Should you have any questions, please feel free to contact us.</p>
        <br>
        <div dir="ltr">
            <span style="font-size:12.8px;font-family:tahoma,sans-serif"><font color="#000000"><span style="font-size:10pt">Finance Department<br></span></font></span>
            <b style="font-size:12.8px"><span lang="EN-US" style="font-size:8pt;font-family:tahoma,sans-serif"><font color="#006600">Wealth Management Cube Limited<br></font></span></b>
            <font color="#000000" face="tahoma, sans-serif"><span style="font-size:10.6667px">Room 804A2, 8/F, World Wide House,19 Des Voeux Road Central, Central, Hong Kong</span></font><br>
            <span lang="EN-US" style="font-size:8pt;font-family:tahoma,sans-serif;color:black">General Line:&nbsp;<a href="tel:+85225169555" value="+85225169555" style="color:rgb(17,85,204)">+852 2516 9555</a>&nbsp;|&nbsp;Fax:&nbsp;<a href="tel:+85225086027" value="+85225086027" style="color:rgb(17,85,204)">+852 2508 6027&nbsp;</a>&nbsp;|&nbsp;Email:&nbsp;</span>
            <span lang="EN-US" style="font-size:8pt;font-family:tahoma,sans-serif"><a href="mailto:finance@wmcubeHK.com" style="color:rgb(17,85,204)">finance@wmcubeHK.com</a><br></span>
            <span style="font-family:tahoma,sans-serif;font-size:8pt">Visit us at:&nbsp;</span><a href="http://www.wmcubehk.com/" style="color:rgb(17,85,204);font-family:tahoma,sans-serif;font-size:8pt">www.wmcubeHK.com</a><br>
            <div style="text-align:start">
                <span style="color:black;font-family:tahoma,sans-serif;font-size:8pt;text-align:justify"><br>
                The message and any attachment are confidential and may be privileged or otherwise protected from disclosure. If you are not the intended recipient you must not copy, distribute, publish, rely on or otherwise use it without our consent. Some of our communications may contain confidential information which it could be a criminal offence for you to disclose or use without authority. If you have received this message in error, please notify us immediately by reply and delete it from your system.</span>
            </div>
        </div>
    </div>"""

    return subject, body, html_body

def create_draft_email(service, files, email_data, max_retries=3):
    """Create email draft with attachments and retry logic"""
    for attempt in range(max_retries):
        try:
            message = MIMEMultipart('alternative')
            message['cc'] = 'ops@wmcubehk.com, finance@wmcubehk.com'
            message['subject'] = email_data['subject']
            
            # Add plain text and HTML versions
            part1 = MIMEText(email_data['body'], 'plain', 'utf-8')
            part2 = MIMEText(email_data['html_body'], 'html', 'utf-8')
            
            message.attach(part1)
            message.attach(part2)
            
            # Add attachments with error handling
            for file_info in files:
                try:
                    attachment = MIMEApplication(file_info['content'], _subtype='pdf')
                    attachment.add_header(
                        'Content-Disposition', 
                        'attachment', 
                        filename=file_info['filename']
                    )
                    message.attach(attachment)
                except Exception as e:
                    st.error(f"Error attaching file {file_info['filename']}: {str(e)}")
                    continue
            
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
            
            draft = service.users().drafts().create(
                userId='me',
                body={'message': {'raw': raw_message}}
            ).execute()
            
            return draft['id']
        
        except Exception as e:
            if attempt < max_retries - 1:
                st.warning(f"Attempt {attempt + 1} failed, retrying...")
                time.sleep(2)
                continue
            st.error(f"Failed to create draft after {max_retries} attempts: {str(e)}")
            return None

def reset_gmail_auth():
    """Reset Gmail authentication"""
    if 'gmail_token' in st.session_state:
        del st.session_state['gmail_token']
    st.success("Gmail authentication has been reset. Please authenticate again.")
    st.experimental_rerun()

def main():
    st.title('Email Draft Generator')
    
    # Add authentication reset button in sidebar
    if st.sidebar.button('Reset Gmail Authentication'):
        reset_gmail_auth()

    service = get_gmail_service()
    if not service:
        st.error("Failed to initialize Gmail service. Please check your authentication.")
        return

    uploaded_files = st.file_uploader("Upload PDF files", type=['pdf'], accept_multiple_files=True)
    currency = st.selectbox("Currency", ["HKD", "USD", "EUR", "GBP"])
    value = st.number_input("Value", min_value=0.0, format="%.2f")

    if st.button("Create Draft") and uploaded_files:
        with st.status("Creating email draft...", expanded=True) as status:
            try:
                subject, body, html_body = create_settlement_template(currency, value)
                
                email_data = {
                    'subject': subject,
                    'body': body,
                    'html_body': html_body
                }

                draft_id = create_draft_email(service, uploaded_files, email_data)
                
                if draft_id:
                    status.update(label="Draft created successfully!", state="complete")
                    st.success("Email draft has been created in your Gmail account.")
                else:
                    status.update(label="Failed to create draft", state="error")
                    st.error("Failed to create email draft. Please try again.")
                    
            except Exception as e:
                status.update(label="Error occurred", state="error")
                st.error(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()
