const CLIENT_ID = "1019972991546-q3ghh6j2lfad6udttk38gf1ef0f727li.apps.googleusercontent.com";
const API_KEY = "AIzaSyCX2BgN8yOJS20aURlr0BNXbz8tZ09VZs0";
const SCOPES = "https://www.googleapis.com/auth/drive.readonly";

let accessToken = null;
let pickerInited = false;
let gisInited = false;

let parsedData = []; //raw volunteers data
let parsedSchoolData = []; // raw school data
let allocationData = []; //processed allocated data

let currentPage = 1;
let rowsPerPage = 50;

let tokenClient; // Global variable to hold the GIS client

// Declare userManager globally but don't initialize it yet
let userManager;

//oidc configuration setting
const oidcConfig = {
    // 1. Your Cognito User Pool Issuer URL
  authority: "https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_RlJKEaPKc", 
  // 2. The App Client ID created inside that User Pool
  client_id: "3riavog3fklq7b6so99rs4vag6",
   // 3. Must match the exact Allowed Callback URL in your Cognito settings
  redirect_uri: "http://localhost/",
  post_logout_redirect_uri: "http://localhost/",
  // 4. Cognito specific requirements
  response_type: "code", 
  scope: "phone openid email",
  userStore: new oidc.WebStorageStateStore({ store: window.localStorage }),

  metadata: {
        issuer: "https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_RlJKEaPKc",
        authorization_endpoint: "https://ap-southeast-1rljkeapkc.auth.ap-southeast-1.amazoncognito.com/oauth2/authorize",
        token_endpoint: "https://ap-southeast-1rljkeapkc.auth.ap-southeast-1.amazoncognito.com/oauth2/token",
        userinfo_endpoint: "https://ap-southeast-1rljkeapkc.auth.ap-southeast-1.amazoncognito.com/oauth2/userInfo",
        end_session_endpoint: "https://ap-southeast-1rljkeapkc.auth.ap-southeast-1.amazoncognito.com/logout",
        jwks_uri: "https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_RlJKEaPKc/.well-known/jwks.json"
    }
};

//temp
const tableData = [
    {
        Priority: 3,
        name: "John Doe",
        sector: "blue",
        address: "Blk 123 Super Long Address Avenue 4, #12-345, Very Long Street Name, Singapore 123456"
    },
    {
        Priority: 1,
        name: "Jane Smith",
        sector: "OC",
        address: "Blk 456 Short Ave"
    }
];

const schooltableData = [
    {
        school_name: "SOUTH VIEW PRIMARY SCHOOL",
        address: "6 CHOA CHU KANG CENTRAL SINGAPORE 689762",
        "max volunteer": "4",
        "Planning Area": "CHOA CHU KANG"
    },
    {
        school_name: "BUKIT PANJANG PRIMARY SCHOOL",
        address: "109 CASHEW ROAD SINGAPORE 679676",
        "max volunteer": "3",
        "Planning Area": "BUKIT PANJANG"
    }
];

// =========================
// New table migration
// =========================
const table = new Tabulator("#dataTable", {

    data: tableData,

    placeholder:"No Data Available", //display message to user on empty table

    layout: "fitColumns",

    height: "550px",

    pagination: true,
    paginationSize: 10,
    paginationSizeSelector: [10, 25, 50, 75, 100],

    movableColumns: false,

    resizableColumnFit: true,

    rowHeader:{formatter:"rownum", headerSort:false, hozAlign:"center", resizable:false, frozen:true, maxWidth:70},

    columns: [

        {
            title: "Priority",
            field: "Priority",
            width: 120,
            editor: "list",
            editorParams: {
                values: [1,2,3,4]
            },
            headerFilter: "list",
            headerFilterParams: {
                values: {
                    "": "All",
                    1: "1",
                    2: "2",
                    3: "3",
                    4: "4"
                }
            },
            resizable:false
        },

        {
            title: "Name",
            field: "name",
            widthGrow: 2,
            headerFilter: "input"
        },

        {
            title: "Sector",
            field: "sector",
            widthGrow: 2,
            headerFilter: "input",
            maxWidth: 150
        },

        {
            title: "Address",
            field: "address",
            widthGrow: 4,
            formatter: "textarea",
            headerFilter: "input"
        }

    ]

});

//Schools table
const tableschool = new Tabulator("#dataTableSchool", {

    data: schooltableData,

    placeholder:"No Data Available", //display message to user on empty table

    layout: "fitColumns",

    height: "550px",

    pagination: true,
    paginationSize: 10,
    paginationSizeSelector: [10, 25, 50],

    movableColumns: false,

    resizableColumnFit: true,

    rowHeader:{formatter:"rownum", headerSort:false, hozAlign:"center", resizable:false, frozen:true, maxWidth:70},

    columns: [

        {
            title: "Name",
            field: "school_name",
            widthGrow: 2,
            headerFilter: "input"
        },

        {
            title: "Address",
            field: "address",
            widthGrow: 4,
            formatter: "textarea",
            headerFilter: "input"
        },

        {
            title: "Max Volunteer",
            field: "max volunteer",
            widthGrow: 2,
            headerFilter: "input",
            maxWidth: 180
        },

        {
            title: "Area",
            field: "Planning Area",
            widthGrow: 1,
            formatter: "textarea",
            headerFilter: "input"
        }

    ]

});

// =========================
// SHOW / HIDE SECTIONS
// =========================
function showSection(id) {
    // sections
    document.querySelectorAll('.content_container')
        .forEach(sec => sec.classList.remove('active'));

    document.getElementById(id).classList.add('active');

    // buttons
    document.querySelectorAll('.menu_btn')
        .forEach(btn => btn.classList.remove('active'));

    const btn = event?.target?.closest('.menu_btn');
    if (btn) btn.classList.add('active');

    if (id === 'VolunteerList') {
        //renderTable(); // refresh table when opened
    }
}


// For popup of file upload
function openModal() {
    document.getElementById("uploadModal").style.display = "flex";
}

function closeModal() {
    document.getElementById("uploadModal").style.display = "none";
}

// LOCAL FILE
function selectLocal() {
    document.getElementById("fileInput").click();
}

document.getElementById("fileInput").addEventListener("change", function(e) {
    const file = e.target.files[0];
    if (!file) return;

    uploadToLambda(file);
});

// GOOGLE section
//Initialize Google drive APIs
// 1. Triggered automatically to load the Google Picker API structure
function gapiLoaded() {
    gapi.load('picker', () => {
        pickerInited = true;
        console.log("Google Picker API loaded successfully.");
    });
}

async function initializePicker() {
    await gapi.client.init({
        apiKey: API_KEY
    });
    pickerInited = true;
}

//Initialize OAuth (Google Identity)
// 2. Triggered automatically to initialize the Google Authentication handler
function gisLoaded() {
    tokenClient = google.accounts.oauth2.initTokenClient({
        client_id: CLIENT_ID, // Uses your Google Client ID declared at the top
        scope: SCOPES,        // Uses your drive.readonly scope
        callback: async (response) => {
            if (response.error !== undefined) {
                console.error("Google Auth Error:", response);
                throw response;
            }
            // Save the direct Google Access token into your variable
            accessToken = response.access_token;
            console.log("Google Drive Token acquired. Opening picker...");
            
            // Now that we have the token, immediately launch the window
            createPicker();
        },
    });
    gisInited = true;
    console.log("Google Identity Services initialized.");
}

//open google drive picker when clicked
// 3. The function attached to your "Select File" button
function selectGoogleDrive() {
    if (!pickerInited || !gisInited) {
        alert("Google services are still loading. Please try again.");
        return;
    }

    // 1. Check if we already have a Google token stored in this session
    if (accessToken === null) {
        console.log("Requesting direct Google Drive token...");
        
        // 2. Grab the email from the active Cognito user session
        userManager.getUser().then(user => {
            const userEmail = user?.profile?.email;
            
            if (userEmail) {
                // FIX: Use 'login_hint' instead of 'hint'
                // AND clear 'prompt' so Google doesn't force the 'select_account' view
                tokenClient.requestAccessToken({ 
                    login_hint: userEmail,
                    prompt: '' 
                });
            } else {
                // Fallback if Cognito hasn't loaded a profile yet
                tokenClient.requestAccessToken();
            }
        }).catch(err => {
            console.error("Could not fetch Cognito profile for hint:", err);
            tokenClient.requestAccessToken();
        });

    } else {
        // Token already exists, open picker instantly
        createPicker();
    }
}

//Create google drive picker
function createPicker() {
    // Restricting view to look for Excel Sheets and JSON files to match your backend workflow goals
    const view = new google.picker.DocsView(google.picker.ViewId.DOCS)
        .setMimeTypes("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel,application/json");

    const picker = new google.picker.PickerBuilder()
        .enableFeature(google.picker.Feature.NAV_HIDDEN)
        .setDeveloperKey(API_KEY) // Uses your Google API key declared at the top
        .setOAuthToken(accessToken) // Passes the fresh Google access token
        .addView(view)
        .setCallback(pickerCallback)
        .build();

    picker.setVisible(true);
}

//Handle the selected file
function pickerCallback(data) {
    if (data.action === google.picker.Action.PICKED) {
        const file = data.docs[0];
        const fileId = file.id;
        const fileName = file.name;

        console.log(`Successfully picked: ${fileName} (ID: ${fileId})`);

        // TODO: Pass this fileId to your AWS Lambda/S3 backend workflow 
        // to download or process the dataset automatically!
        downloadDriveFile(fileId, fileName);
    }
}
//Download file from google
async function downloadDriveFile(fileId, fileName) {
    const response = await fetch(
        `https://www.googleapis.com/drive/v3/files/${fileId}?alt=media`,
        {
            headers: {
                Authorization: `Bearer ${accessToken}`
            }
        }
    );

    const blob = await response.blob();

    // convert to File object
    const file = new File([blob], fileName);

    // send to your Lambda
    uploadToLambda(file);
}
//End of google drive section

//upload file to lambda
async function uploadToLambda(file) {
    try {
        console.log(`Starting upload sequence for: ${file.name}`);

        // 1. Ensure the user is logged in and extract their Cognito ID Token
        const user = await userManager.getUser();
        if (!user || !user.id_token) {
            alert("Authentication token missing. Please sign in first.");
            return;
        }
        const idToken = user.id_token;

        // 2. Request a Presigned Upload URL from your API Gateway endpoint
        // TODO: Replace with your actual deployed API Gateway stage URL
        const apiGatewayEndpoint = "https://YOUR_API_ID.execute-api.ap-southeast-1.amazonaws.com/prod/upload-request";

        const urlRequest = await fetch(apiGatewayEndpoint, {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${idToken}`, // Secure connection via Cognito
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                fileName: file.name,
                fileType: file.type || "application/octet-stream"
            })
        });

        if (!urlRequest.ok) {
            const errorText = await urlRequest.text();
            throw new Error(`Backend rejected URL request: ${errorText}`);
        }

        const urlData = await urlRequest.json();
        const presignedS3Url = urlData.uploadUrl;
        console.log("Presigned S3 upload URL successfully generated.");

        // 3. Upload the file binary directly into Amazon S3
        const s3UploadResponse = await fetch(presignedS3Url, {
            method: "PUT", // S3 Presigned URLs strictly require a PUT request
            headers: {
                "Content-Type": file.type || "application/octet-stream"
            },
            body: file // Streams the raw binary file context directly
        });

        if (s3UploadResponse.ok) {
            alert(`🎉 ${file.name} successfully uploaded to S3! Code execution will begin.`);
            console.log(`File registered in storage bucket under key: ${urlData.s3Key}`);
            
            // NOTE FOR GOAL 2: Here is where you can later trigger your 
            // WebSocket listener to watch for processing progress updates.
        } else {
            throw new Error(`S3 upload failed with status code: ${s3UploadResponse.status}`);
        }

    } catch (err) {
        console.error("❌ Data upload pipeline failed:", err);
        alert(`Upload error: ${err.message}`);
    }
}

//End of file upload section

// =========================
// RENDER TABLE & UI
// =========================
function renderTable() {
    const tbody = document.querySelector("#dataTable tbody");
    tbody.innerHTML = ""; // Clear existing rows

    const start = (currentPage - 1) * rowsPerPage;
    const end = start + parseInt(rowsPerPage);
    const paginatedData = parsedData.slice(start, end);

    paginatedData.forEach((row, index) => {
        const globalIndex = start + index; // Track position in the main array
        const tr = document.createElement("tr");

        // Priority Dropdown
        const priorityTd = document.createElement("td");
        priorityTd.innerHTML = `
            <select onchange="changePriority(${globalIndex}, this.value)">
                <option value="1" ${row['Priority'] === 1 ? 'selected' : ''}>1</option>
                <option value="2" ${row['Priority'] === 2 ? 'selected' : ''}>2</option>
                <option value="3" ${row['Priority'] === 3 ? 'selected' : ''}>3</option>
                <option value="4" ${row['Priority'] === 4 ? 'selected' : ''}>4</option>
            </select>
        `;

        // Text Columns
        const nameTd = document.createElement("td");
        nameTd.innerText = row['name'] || '';

        const sectorTd = document.createElement("td");
        sectorTd.innerText = row['Sector'] || '';

        const addressTd = document.createElement("td");
        addressTd.innerText = row['address'] || '';

        tr.appendChild(priorityTd);
        tr.appendChild(nameTd);
        tr.appendChild(sectorTd);
        tr.appendChild(addressTd);
        tbody.appendChild(tr);
    });

    document.getElementById("pageInfo").innerText = `Page ${currentPage}`;
    updateSummary();
}

// Update the main data array when a dropdown is changed
function changePriority(globalIndex, newValue) {
    parsedData[globalIndex]['Priority'] = parseInt(newValue);
    updateSummary(); // Refresh the counts immediately
}

// =========================
// SUMMARY DASHBOARD
// =========================
function updateSummary() {
    let counts = { 1: 0, 2: 0, 3: 0, 4: 0 };
    
    parsedData.forEach(row => {
        counts[row['Priority']]++;
    });

    document.getElementById("sumTotal").innerText = parsedData.length;
    document.getElementById("sumP1").innerText = counts[1];
    document.getElementById("sumP2").innerText = counts[2];
    document.getElementById("sumP3").innerText = counts[3];
    document.getElementById("sumP4").innerText = counts[4];

    document.getElementById("summaryTotal").innerText = parsedData.length;
    document.getElementById("summary1").innerText = counts[1];
    document.getElementById("summary2").innerText = counts[2];
    document.getElementById("summary3").innerText = counts[3];
    document.getElementById("summary4").innerText = counts[4];
}

function updateSchoolSummary() {
    let totalSchool = 0;
    let openSlots = 0;
    
    parsedSchoolData.forEach(row => {
        totalSchool++;
        let p = parseInt(row['max volunteer']);
        openSlots += p;
    });

    document.getElementById("sumTotalSchool").innerText = totalSchool;

    document.getElementById("massAssignSchoolTotal").innerText = totalSchool;
    if (allocationData?.length === 0) {
        document.getElementById("schoolOpenSlots").innerText = openSlots;
        document.getElementById("sumS1").innerText = 0;
        document.getElementById("sumS2").innerText = totalSchool;
    }

}

// =========================
// SAVING LOGIC (DRAFT)
// =========================
function saveData() {
    // This is where we will eventually put the fetch() call to send 
    // parsedData to your Python backend or save it as a new Excel file.
    console.log("💾 Manual Save Triggered! Ready to send to backend.", parsedData);
    alert("Data saved! (Check console for payload)");
}

// Auto-Save Trigger (Fires every 60,000 milliseconds / 1 minute)
// Uncomment the line below when you are ready to activate it!
// setInterval(saveData, 60000);

// =========================
// FILE INPUT
// =========================
// DEFAULT PAGE
showSection("VolunteerList");

    // FILE UPLOAD
    document.getElementById("tableFileInput")
        .addEventListener("change", function (e) {

        console.log("File Selected!");

        const file = e.target.files[0];

         if (!file) return;

         const reader = new FileReader();

         reader.onload = function(event) {
            const data = new Uint8Array(event.target.result);
            const workbook = XLSX.read(data, { type: 'array' });
            const sheet = workbook.SheetNames[0];
            const worksheet = workbook.Sheets[sheet];

            const rawData = XLSX.utils.sheet_to_json(worksheet);

            // DATA CLEANING: Ensure Priority is 1, 2, 3, or 4
            parsedData = rawData.map(row => {
                let p = parseInt(row['Priority']);
                if (isNaN(p) || p < 1 || p > 4) {
                    row['Priority'] = 4; // Default to 4 if empty or invalid
                } else {
                    row['Priority'] = p;
                }
                return row;
            });
            
            // Data cleaning for address
            parsedData = parsedData.map(row => {
            if (row['address']) {
                row['address'] = row['address'].replace(/#\S+\s?/, '');
            }
            return row;
        });

            table.setData(parsedData);
            updateSummary();
        };

        reader.readAsArrayBuffer(file);
        event.target.value = "";
    });

    document.getElementById("tableSchoolFileInput")
        .addEventListener("change", function (e) {

        console.log("File Selected!");

        const file = e.target.files[0];

         if (!file) return;

         const reader = new FileReader();

         reader.onload = function(event) {
            const data = new Uint8Array(event.target.result);
            const workbook = XLSX.read(data, { type: 'array' });
            const sheet = workbook.SheetNames[0];
            const worksheet = workbook.Sheets[sheet];

            const rawData = XLSX.utils.sheet_to_json(worksheet);
            parsedSchoolData = rawData;

            tableschool.setData(parsedSchoolData);
            updateSchoolSummary();
        };

        reader.readAsArrayBuffer(file);
        event.target.value = "";
    });


// Core functions for button actions
async function handleSignIn() {
    try {
        await userManager.signinRedirect();
    } catch (err) {
        console.error("Sign in redirect failed:", err);
    }
}

async function handleSignOut() {
    try {
        // Force the library to append the custom parameters AWS Cognito demands
        await userManager.signoutRedirect({
            extraQueryParams: {
                client_id: oidcConfig.client_id,
                logout_uri: oidcConfig.post_logout_redirect_uri
            }
        });
    } catch (err) {
        console.error("Sign out redirect failed:", err);
    }
}

async function initAuth() {
    // 1. TEMPORARY DIAGNOSTICS - Add these lines here:
    console.log("🔍 [Debug] Current URL on page load:", window.location.href);
    
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has('error')) {
        console.error("🚨 COGNITO RETURNED AN OAUTH ERROR:");
        console.error("Type:", urlParams.get('error'));
        console.error("Description:", urlParams.get('error_description'));
        return; // Stop execution so you can read the error
    }
    // --------------------------------------------------

     // Check if the OIDC library loaded successfully
    if (typeof oidc === 'undefined') {
        console.error("Critical Error: The oidc library failed to load. Please check your HTML script tags or CDN link.");
        return;
    }
    
    // Initialize after we are certain 'oidc' is loaded
    userManager = new oidc.UserManager(oidcConfig);

    // 1. Check if the URL has an authentication code from AWS Cognito
    //const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has('code')) {
        console.log("Detected incoming login code from Cognito. Attempting token exchange...");
        try {
            console.log("Found authentication code in URL. Processing login callback...");
            // Process the incoming authorization code and save the user tokens
            await userManager.signinRedirectCallback();
            
            // Clean up the URL query parameters from the address bar so it looks pristine
            window.history.replaceState({}, document.title, window.location.pathname);
            console.log("Callback successful! Token state established.");
        } catch (err) {
            console.error("🚨 === COGNITO CALLBACK EXCHANGE FAILED ===");
            console.error("Error Message:", err.message);
            console.error("Error Details:", err);
            console.error("=========================================");
            // Stop execution here if there's an error so the URL doesn't clear, allowing you to see the problem
            return;
        }
    }

    // 2. Evaluate current user state to update the UI elements
    userManager.getUser().then(function (user) {
        const button = document.getElementById("signIn") || document.getElementById("signOut");
        if (user) {
            // User is actively logged in
            document.getElementById("email").textContent = user.profile?.email || "";
            document.getElementById("access-token").textContent = user.access_token;
            document.getElementById("id-token").textContent = user.id_token;
            document.getElementById("refresh-token").textContent = user.refresh_token || "";
             
            if (button) {
                button.textContent = "Log out";
                button.id = "signOut";
                // Clear old bindings to prevent stacking identical listeners
                button.removeEventListener("click", handleSignIn);
                button.addEventListener("click", handleSignOut);
            }
        } else {
            console.log("No active user session found.");
            // User is logged out
            document.getElementById("email").textContent = "";
            document.getElementById("access-token").textContent = "";
            document.getElementById("id-token").textContent = "";
            document.getElementById("refresh-token").textContent = "";
                
            if (button) {
                button.textContent = "Sign In";
                button.id = "signIn";
                // Clear old bindings to prevent stacking identical listeners
                button.removeEventListener("click", handleSignOut);
                button.addEventListener("click", handleSignIn);
            }
        }
        }).catch(err => {
            console.error("Error loading user state:", err);
        });
}

// Safely run the initialization after the window fully loads
window.addEventListener('load', initAuth);

//to run at the start once javascript is loaded
gapiLoaded();
gisLoaded();
//loadTable();