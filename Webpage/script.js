// ==========================================
// script.js - Core Logic, Auth, & AWS Integrations
// ==========================================

const CLIENT_ID = "1019972991546-q3ghh6j2lfad6udttk38gf1ef0f727li.apps.googleusercontent.com";
const API_KEY = "AIzaSyCX2BgN8yOJS20aURlr0BNXbz8tZ09VZs0";
const SCOPES = "https://www.googleapis.com/auth/drive.readonly";

let accessToken = null;
let pickerInited = false;
let gisInited = false;
let tokenClient; 
let userManager;

// Source of Truth Data Arrays
let parsedData = []; //volunteer data
let parsedSchoolData = []; // school data
let allocationData = []; //processed data

let currentPage = 1;
let rowsPerPage = 50;

// =========================
// OIDC & AWS COGNITO CONFIG
// =========================
const oidcConfig = {
  authority: "https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_RlJKEaPKc", 
  client_id: "3riavog3fklq7b6so99rs4vag6",
  redirect_uri: "https://ikrion.github.io/NDPschoolTagging/",  //change if uploading to github
  post_logout_redirect_uri: "https://ikrion.github.io/NDPschoolTagging/",  //change if uploading to github
  response_type: "code", 
  scope: "phone openid email",
  userStore: new oidc.WebStorageStateStore({ store: window.localStorage }),
  monitorSession: true,
  metadata: {
        issuer: "https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_RlJKEaPKc",
        authorization_endpoint: "https://ap-southeast-1rljkeapkc.auth.ap-southeast-1.amazoncognito.com/oauth2/authorize",
        token_endpoint: "https://ap-southeast-1rljkeapkc.auth.ap-southeast-1.amazoncognito.com/oauth2/token",
        userinfo_endpoint: "https://ap-southeast-1rljkeapkc.auth.ap-southeast-1.amazoncognito.com/oauth2/userInfo",
        end_session_endpoint: "https://ap-southeast-1rljkeapkc.auth.ap-southeast-1.amazoncognito.com/logout",
        jwks_uri: "https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_RlJKEaPKc/.well-known/jwks.json"
    }
};

// =========================
// CORE DATA UPDATES
// =========================

// Exposed to window so Tabulator (in ui.js) can send edit events back here
window.handlePriorityEdit = function(rowId, newPriority) {
    // Find the edited row in our source array and update it
    const row = parsedData.find(r => r.id === rowId);
    if (row) {
        row.Priority = parseInt(newPriority);
        updateSummary(); // Recalculate dashboard totals
    }
};

function updateSummary() {
    // Call UI file to update visual dashboard
    updateSummaryUI(parsedData); 
}

function updateSchoolSummary() {
    // Call UI file to update visual dashboard
    updateSchoolSummaryUI(parsedSchoolData, allocationData); 
}

// =========================
// FILE PROCESSING (EXCEL TO JSON)
// =========================
function selectLocal() { 
    // This button works universally now
    document.getElementById("fileInput").click(); 
}

function bindEventListeners() {
    document.getElementById("fileInput")?.addEventListener("change", function(e) {
        const file = e.target.files[0];
        if (file) processUploadedFile(file);
        e.target.value = ""; // Reset the input so the user can upload the same file again if needed
    });
}

function storeCache(key, data) {
  try {
    const cachePayload = {
      timestamp: Date.now(),
      data: data
    };
    localStorage.setItem(key, JSON.stringify(cachePayload));
    return true;
  } catch (error) {
    console.error("Failed to save to localStorage (storage might be full):", error);
    return false;
  }
}

function getCache(key) {
  const HOURS = 6 * 60 * 60 * 1000; // 6 hours in milliseconds
  
  try {
    const cachedItem = localStorage.getItem(key);
    if (!cachedItem) return null; // No cache found

    const { timestamp, data } = JSON.parse(cachedItem);
    
    // Check if the cache is still valid
    if (Date.now() - timestamp < HOURS) {
      return data; 
    }
    
    // Optional: Clean up expired cache to free up space
    localStorage.removeItem(key); 
    return null;
  } catch (error) {
    console.error("Failed to read or parse cache:", error);
    return null;
  }
}

async function processUploadedFile(file) {
    if (!file) return;

    const reader = new FileReader();
    //only upload immediatly if user is logged in
    const user = await userManager.getUser();

    reader.onload = function(event) {
        const data = new Uint8Array(event.target.result);
        const workbook = XLSX.read(data, { type: 'array' });
        const rawData = XLSX.utils.sheet_to_json(workbook.Sheets[workbook.SheetNames[0]]);

        // ROUTE 1: Volunteer Page is Active
        if (currentActiveSection === "VolunteerList") {
            parsedData = rawData.map((row, index) => {
                let p = parseInt(row['Priority']);
                row['Priority'] = (isNaN(p) || p < 1 || p > 4) ? 1 : p;
                row['id'] = index; // Unique ID for Tabulator
                return {
                    id: index,
                    Priority: row['Priority'],
                    Name: row['name'] || row['Name'] || row['Full name'] || row['Full Name'] || '',
                    Sector: row['sector'] || row['Sector'] ||'',
                    Address: (
                                row['Address'] ||
                                row['address'] ||
                                row['Home Address'] ||
                                row['Residential Address'] ||
                                ''
                            )
                            .replace(/\s*#\S+/g, '')
                            .replace(/\s+/g, ' ')
                            .trim()
                };
            });
            
            loadVolunteerDataToUI(parsedData); 
            //updateSummary();
            if (user && user.id_token) {
                uploadToLambda(parsedData, "users.json");
            }
            else { //Guest save to cache
                const CACHE_KEY = "my_volunteer_data";
                if (storeCache(CACHE_KEY, parsedData))
                    console.info("Saved volunteer data to cache!");
            }
        } 
        // ROUTE 2: School Page is Active
        else if (currentActiveSection === "SchoolList") {
            parsedSchoolData = rawData.map((row, index) => {
                row['id'] = index; // Unique ID for Tabulator
                return {
                    id: index,
                    SchoolName: row['school_name'] || row['school'] || row['school name'] || row['School'] || row['School Name'] || row['School name'] || '',
                    Address: (
                                row['Address'] ||
                                row['address'] ||
                                row['Home Address'] ||
                                row['Residential Address'] ||
                                ''
                            )
                            .replace(/\s*#\S+/g, '')
                            .replace(/\s+/g, ' ')
                            .trim(),
                    'max volunteer': row['Max Volunteer'] || row['max volunteer'] || row['Volunteer Needed'] || '',
                    "Planning Area": row['Area'] || row['area'] ||''
                    
                };
            });;
            
            loadSchoolDataToUI(parsedSchoolData); 
            //updateSchoolSummary();
            if (user && user.id_token) {
                uploadToLambda(parsedSchoolData, "schools.json");
            }
            else { //Guest save to cache
                const CACHE_KEY = "my_school_data";
                storeCache(CACHE_KEY, parsedSchoolData);
                console.info("Saving school data to cache!");
            }
        }
        
    };

    closeModal();
    reader.readAsArrayBuffer(file);
}

// =========================
// GOOGLE DRIVE APIs
// =========================
function gapiLoaded() {
    gapi.load('picker', () => { pickerInited = true; });
}

async function initializePicker() {
    await gapi.client.init({ apiKey: API_KEY });
    pickerInited = true;
}

function gisLoaded() {
    tokenClient = google.accounts.oauth2.initTokenClient({
        client_id: CLIENT_ID,
        scope: SCOPES,
        callback: async (response) => {
            if (response.error !== undefined) throw response;
            accessToken = response.access_token;
            createPicker();
        },
    });
    gisInited = true;
}

function selectGoogleDrive() {
    if (!pickerInited || !gisInited) return alert("Google services loading.");
    if (accessToken === null) {
        userManager.getUser().then(user => {
            const userEmail = user?.profile?.email;
            if (userEmail) {
                tokenClient.requestAccessToken({ login_hint: userEmail, prompt: '' });
            } else {
                tokenClient.requestAccessToken();
            }
        }).catch(err => tokenClient.requestAccessToken());
    } else {
        createPicker();
    }
}

function createPicker() {
    const view = new google.picker.DocsView(google.picker.ViewId.DOCS)
        .setMimeTypes("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel,application/json");
    const picker = new google.picker.PickerBuilder()
        .enableFeature(google.picker.Feature.NAV_HIDDEN)
        .setDeveloperKey(API_KEY)
        .setOAuthToken(accessToken)
        .addView(view)
        .setCallback(pickerCallback)
        .build();
    picker.setVisible(true);
}

function pickerCallback(data) {
    if (data.action === google.picker.Action.PICKED) {
        const file = data.docs[0];
        downloadDriveFile(file.id, file.name);
    }
}

async function downloadDriveFile(fileId, fileName) {
    const response = await fetch(`https://www.googleapis.com/drive/v3/files/${fileId}?alt=media`, {
        headers: { Authorization: `Bearer ${accessToken}` }
    });
    const file = new File([await response.blob()], fileName);
    
    // Send the downloaded Google Drive file to our router to update the UI
    processUploadedFile(file);
}

// =========================
// AWS LAMBDA / FILE UPLOAD
// =========================
async function uploadToLambda(data, filename) {
    try {
        const apiGatewayEndpoint = "https://yk056aw14b.execute-api.ap-southeast-1.amazonaws.com/default/NDP_SchoolTagging";
        const lambdaFunctionURL = "https://mmhsmpwet5fnxxszmelfguxxjy0aigsz.lambda-url.ap-southeast-1.on.aws/";
        const user = await userManager.getUser();

        if (user && user.id_token) {
            // S3 Flow (Logged In)
            const idToken = user.id_token;
            const userId = user.profile.sub; 

            const urlRequest = await fetch(apiGatewayEndpoint, {
                method: "POST",
                headers: { "Authorization": `Bearer ${idToken}`, "Content-Type": "application/json"},
                body: JSON.stringify({ action: "upload", user_id: userId, filename: filename})
            });

            if (!urlRequest.ok) throw new Error("Backend rejected URL request");
            const urlData = await urlRequest.json();
            
            const presignedS3Url = urlData.uploadUrl; 
            console.log("this is my presigned url: ", presignedS3Url);
            // ✅ convert JS object → JSON file
            const payload = new Blob(
                [JSON.stringify(data)],
                { type: "application/json" }
            );

            console.log("this is my data file: ", payload);
            const s3UploadResponse = await fetch(presignedS3Url, {
                method: "PUT",
                 headers: { "Content-Type": "application/json"},
                body: payload 
            });

            if (s3UploadResponse.ok) alert(`🎉 ${filename} successfully uploaded!`);
            
        }
    } catch (err) {
        alert(`Pipeline error: ${err.message}`);
    }
}

// This download is only for signed in user
async function downloadFromLambda(filename) {
    try {
        const apiGatewayEndpoint = "https://yk056aw14b.execute-api.ap-southeast-1.amazonaws.com/default/NDP_SchoolTagging";
        const lambdaFunctionURL = "https://mmhsmpwet5fnxxszmelfguxxjy0aigsz.lambda-url.ap-southeast-1.on.aws/";
        const user = await userManager.getUser();

        if (user && user.id_token) {
            // S3 Flow (Logged In)
            const idToken = user.id_token;
            const userId = user.profile.sub; 

            // 1. Ask the backend for the download ticket
            const urlRequest = await fetch(apiGatewayEndpoint, {
                method: "POST",
                headers: { 
                    "Authorization": `Bearer ${idToken}`, 
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ 
                    action: "download", 
                    user_id: userId, 
                    filename: filename
                })
            });

            if (!urlRequest.ok) throw new Error("Backend rejected URL request");
            const urlData = await urlRequest.json();
            
           // 2. Grab the correct key from your Python response
            const presignedS3Url = urlData.download_url; 
            console.log("This is my secure S3 link: ", presignedS3Url);

            // 3. FETCH THE DATA DIRECTLY (No file downloads!)
            const s3Response = await fetch(presignedS3Url);
            if (!s3Response.ok) throw new Error("Failed to read data from S3 bucket.");
            
            // Parse the data back into a JavaScript Object
            const processedData = await s3Response.json();

            // 4. Save to Browser Cache (Session Storage)
            // This keeps the data safe even if they accidentally refresh the page, 
            // but automatically deletes it when they close the browser tab.
            //sessionStorage.setItem('cachedAllocationData', JSON.stringify(processedData));
            
            
            if (filename === "users.json")
            {
                console.info(`fetching ${filename} data from AWS!`);
                const CACHE_KEY1 = `${userId}_my_volunteer_data`;
                parsedData = processedData;
                storeCache(CACHE_KEY1, parsedData);
                loadVolunteerDataToUI(parsedData);
            } else if (filename === "schools.json") {
                console.info(`fetching ${filename} data from AWS!`);
                const CACHE_KEY2 = `${userId}_my_school_data`;
                parsedSchoolData = processedData;
                storeCache(CACHE_KEY2, parsedSchoolData);
                loadSchoolDataToUI(parsedSchoolData);
            } else {
                console.info(`fetching ${filename} data from AWS!`);
                const CACHE_KEY3 = `${userId}_my_allocation_data`;
                allocationData = processedData;
                storeCache(CACHE_KEY3, allocationData);
                loadAllocationDataToUI(allocationData);
            }
            
        }
    } catch (err) {
        console.error(`Pipeline error:${filename} download from S3 is giving ${err.message}`);
    }
}

// =========================
// OIDC AUTHENTICATION
// =========================
async function handleSignIn() {
    try { await userManager.signinRedirect(); } catch (err) { console.error(err); }
}

async function handleSignOut() {
    try {
        await userManager.signoutRedirect({
            extraQueryParams: { client_id: oidcConfig.client_id, logout_uri: oidcConfig.post_logout_redirect_uri }
        });
        alert("Sign out successful!")
    } catch (err) { console.error(err); }
}

async function initAuth() {
    try {
        const urlParams = new URLSearchParams(window.location.search);

        if (urlParams.has('error')) {
            console.error(urlParams.get('error'));
            return;
        }

        if (typeof oidc === 'undefined') {
            console.error("OIDC library missing.");
            return;
        }

        userManager = new oidc.UserManager(oidcConfig);

        // -----------------------------
        // 1. SAFE CALLBACK HANDLING
        // -----------------------------
        const isCallback =
            window.location.search.includes("code") &&
            window.location.search.includes("state");

        if (isCallback) {
            try {
                await userManager.signinRedirectCallback();

                // Clean URL immediately (prevents re-processing on refresh)
                window.history.replaceState({}, document.title, window.location.pathname);

            } catch (err) {
                console.warn("⚠️ Primary callback failed, attempting recovery...", err);

                // 🔥 Recovery attempt (fixes missing state issues)
                sessionStorage.clear();

                try {
                    await userManager.signinRedirectCallback();
                    window.history.replaceState({}, document.title, window.location.pathname);
                } catch (err2) {
                    console.error("❌ Callback permanently failed:", err2);

                    // Force user back to login cleanly
                    await userManager.removeUser();
                    updateAuthUI(null, handleSignIn, handleSignOut);
                    return;
                }
            }
        }

        // -----------------------------
        // 2. SAFE USER LOAD (multi-layer recovery)
        // -----------------------------
        let user = await userManager.getUser();

        // fallback: silent login if session exists but getUser fails
        if (!user || user.expired) {
            try {
                user = await userManager.signinSilent();
                console.log("🔄 Silent login restored session");
            } catch (silentErr) {
                user = null;
            }
        }

        // -----------------------------
        // 3. GUEST MODE
        // -----------------------------
        if (!user || user.expired) {
            console.info("🟡 Guest mode: loading cached global data");

            const CACHE_KEY1 = "my_volunteer_data";
            const CACHE_KEY2 = "my_school_data";
            const CACHE_KEY3 = "my_allocation_data";

            parsedData = getCache(CACHE_KEY1);
            parsedSchoolData = getCache(CACHE_KEY2);
            allocationData = getCache(CACHE_KEY3);

            if (parsedData) loadVolunteerDataToUI(parsedData);
            if (parsedSchoolData) loadSchoolDataToUI(parsedSchoolData);
            if (allocationData) loadAllocationDataToUI(allocationData);
        }

        // -----------------------------
        // 4. LOGGED-IN MODE
        // -----------------------------
        else {
            const userId = user.profile.sub;

            console.info("🟢 Logged in: loading user-specific cache");

            const CACHE_KEY1 = `${userId}_my_volunteer_data`;
            const CACHE_KEY2 = `${userId}_my_school_data`;
            const CACHE_KEY3 = `${userId}_my_allocation_data`;

            parsedData = getCache(CACHE_KEY1);
            parsedSchoolData = getCache(CACHE_KEY2);
            allocationData = getCache(CACHE_KEY3);

            if (parsedData) {
                loadVolunteerDataToUI(parsedData);
            } else {
                await downloadFromLambda("users.json");
            }

            if (parsedSchoolData) {
                loadSchoolDataToUI(parsedSchoolData);
            } else {
                await downloadFromLambda("schools.json");
            }

            if (allocationData) {
                loadAllocationDataToUI(allocationData);
            } else {
                await downloadFromLambda("tagged_allocations.json");
            }
        }

        // -----------------------------
        // 5. ALWAYS UPDATE UI LAST
        // -----------------------------
        updateAuthUI(user, handleSignIn, handleSignOut);

    } catch (err) {
        console.error("🚨 initAuth crashed:", err);

        // fallback safety net
        updateAuthUI(null, handleSignIn, handleSignOut);
    }
}

async function safeAuthInit(userManager) {
    try {
        // 1. Detect callback attempt
        const url = new URL(window.location.href);
        const hasAuthResponse = url.searchParams.has("code") && url.searchParams.has("state");

        if (hasAuthResponse) {
            console.log("🔐 Processing login callback...");

            const user = await userManager.signinRedirectCallback();

            // Clean URL after success
            window.history.replaceState({}, document.title, window.location.pathname);

            return user;
        }

        // 2. Try silent restore first
        let user = await userManager.getUser();

        if (user && !user.expired) {
            console.log("✅ Existing session found");
            return user;
        }

        // 3. Try silent renew (bulletproof layer)
        try {
            user = await userManager.signinSilent();
            console.log("🔄 Silent login restored session");
            return user;
        } catch (silentErr) {
            console.log("⚠️ Silent login failed, user must sign in");
        }

        return null;

    } catch (err) {
        console.error("❌ Auth recovery failed:", err);

        // IMPORTANT: clear broken state and recover
        sessionStorage.clear();

        return null;
    }
}

async function safeSigninCallback(userManager) {
    const url = new URL(window.location.href);

    if (!url.searchParams.has("code")) {
        return null;
    }

    try {
        return await userManager.signinRedirectCallback();
    } catch (err) {
        console.warn("⚠️ First callback attempt failed:", err);

        // 🔁 Recovery attempt (state might be lost)
        sessionStorage.clear();

        try {
            return await userManager.signinRedirectCallback();
        } catch (err2) {
            console.error("❌ Callback permanently failed:", err2);

            // Force re-login
            await userManager.signinRedirect();
            return null;
        }
    }
}

async function emergencyAuthRecovery() {
    console.log("🚨 Attempting emergency recovery...");

    sessionStorage.clear();

    try {
        const user = await userManager.getUser();

        if (user) return user;

        await userManager.removeUser();
    } catch (e) {
        console.error("Recovery failed:", e);
    }

    return null;
}

// ==========================================
// DATA PROCESSING TRIGGER
// ==========================================
async function startDataProcessing() {
    try {
        // 1. Switch the UI to the processing screen
        toggleProcessingUI("processing");

        // Endpoints configured from your previous architecture
        const apiGatewayEndpoint = "https://yk056aw14b.execute-api.ap-southeast-1.amazonaws.com/default/NDP_SchoolTagging";
        const lambdaFunctionURL = "https://mmhsmpwet5fnxxszmelfguxxjy0aigsz.lambda-url.ap-southeast-1.on.aws/";

        // Get current user state
        const user = await userManager.getUser();

        // Get the total user count
        let total = parsedData.length;
        let currentRepeatCount = 0;
        let prevCount = 0;

        // Inform UI that processing has started (e.g., show a loading spinner)
        //if (window.showProcessingStateUI) window.showProcessingStateUI(true, total);

        let finalProcessedData = null;

        // ==========================================
        // ROUTE A: LOGGED-IN USER (Triggers S3-based backend processing)
        // ==========================================
        if (user && user.id_token) {
            console.log("Authenticated User: Initiating backend S3 processing...");
            
            const startResponse = await fetch(apiGatewayEndpoint, {
                method: "POST",
                headers: {
                    "Authorization": `Bearer ${user.id_token}`,
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    action: "process_start",
                    user_id: user.profile.sub
                })
            });

            if (!startResponse.ok) throw new Error("Failed to start processing on the backend.");
            
            const startData = await startResponse.json();
            const jobId = startData.job_id;
            console.log("process msg: ", startData.message);

            // 3. Begin Polling DynamoDB every 2.5 seconds
            const pollInterval = setInterval(async () => {
                try {
                    // Call a new "check_progress" route on your backend
                    const progressResponse = await fetch(apiGatewayEndpoint, {
                        method: "POST",
                        headers: {
                            "Authorization": `Bearer ${user.id_token}`,
                            "Content-Type": "application/json"
                        },
                        body: JSON.stringify({
                            action: "check_progress",
                            job_id: jobId
                        })
                    });

                    let progressData = await progressResponse.json();
                    
                    // Assuming DynamoDB returns { ProcessUser: 45, TotalUser: 133, status: "processing" }
                    const current = progressData.ProcessUser || 0;
                    
                    if (current === prevCount)
                    {
                        currentRepeatCount++;
                    }
                    else
                    {
                        currentRepeatCount = 0;
                    }

                    if (total != progressData.TotalUser)
                    {
                        total = progressData.TotalUser || 0;
                    }

                    if (currentRepeatCount >= 50)
                    {
                        toggleProcessingUI("fail",0);
                        clearInterval(pollInterval);
                        console.log("Progress check stop due to repeated 0 for 2 mins")
                    }

                    prevCount = current;

                    // Update the visual bar
                    updateProgressUI(current, total);

                    // 4. Check if finished
                    if (progressData.status === "completed") {
                        clearInterval(pollInterval);
                        
                        // Extracts exactly what Python saved in ':result': final_processed_data
                        let schoolAssignments = progressData.result; 
                        
                        // Parse if it was saved or returned as a raw JSON string escape sequence
                        if (typeof schoolAssignments === "string") {
                            schoolAssignments = JSON.parse(schoolAssignments);
                        }

                        if (window.loadAllocationDataToUI) {
                            // Match schoolInfo to your local frontend parsedSchoolData state
                            const schoolInfo = window.parsedSchoolData || {};
                            
                            // Fire the layout engine with both data points
                            window.loadAllocationDataToUI(schoolAssignments, schoolInfo);
                        }
                    
                        if (typeof toggleProcessingUI === "function") {
                            toggleProcessingUI("finished", schoolAssignments);
                        }
                        alert("Processing Complete!");
                    } else if (progressData.status && progressData.status.startsWith("failed")) {
                        // Instantly break out of loop if Python hit the except block and flagged a failure
                        clearInterval(pollInterval);
                        if (typeof toggleProcessingUI === "function") {
                            toggleProcessingUI("fail",0);
                        }
                        alert(`Backend Processing Failed: ${progressData.status}`);
                    }

                } catch (pollErr) {
                    console.error("Polling error (Retrying...):", pollErr);
                }
            }, 2500); // 2500 milliseconds = 2.5 seconds

        } 
        // ==========================================
        // ROUTE B: GUEST USER (Sends data via payload, uses Function URL)
        // ==========================================
        else {
            console.log("Guest User: Sending raw data to Function URL for memory processing...");
            
            // --- FUTURE IMPLEMENTATION: GUEST PROGRESS ---
            // Because this is a single open connection holding for up to 15 minutes,
            // progress tracking requires either Server-Sent Events (SSE) or a simulated 
            // visual progress bar on the frontend based on an estimated time.
            // ------------------------------------------------

            const response = await fetch(lambdaFunctionURL, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    action: "process_guest",
                    user_data: parsedData,          // Volunteer arrays
                    school_data: parsedSchoolData   // School arrays
                })
            });

            if (!response.ok) throw new Error("Guest processing failed or timed out.");

            const current = 0;

            // Update the visual bar
            updateProgressUI(current, total);

            const resultData = await response.json();
            let parsedResponse = typeof resultData === "string" ? JSON.parse(resultData) : resultData;
            
            // Extract the rows object from AWS payload
            let schoolAssignments = parsedResponse.processed_json || parsedResponse;

            const CACHE_KEY = "my_allocation_data";
            storeCache(CACHE_KEY, schoolAssignments);
            
            if (typeof schoolAssignments === "string") {
                allocationData = JSON.parse(schoolAssignments);
            }

            // ==========================================
            // FINAL STEP: UPDATE THE UI
            // ==========================================
            if (allocationData) {
                console.log("Processing complete! Updating Allocation Table...");
                toggleProcessingUI("finished", allocationData);
                if (window.loadAllocationDataToUI) {
                    // Assuming 'parsedSchoolData' is accessible globally or stored in your state
                    window.loadAllocationDataToUI(allocationData, parsedSchoolData);
                }
            }
        }
    } catch (err) {
        toggleProcessingUI("fail");
        console.error("Processing Error:", err);
        alert("An error occurred during data processing: " + err.message);
    } finally {
        // Stop the loading spinner
        //if (window.showProcessingStateUI) window.showProcessingStateUI(false);
    }
}

//for selected processing
function processSelectedUsers() {
    console.log(selectedUsers);

    selectedUsers.forEach(user => {
        console.log(
            `Processing ${user.Name} (${user.id})`
        );
    });
}

// =========================
// INITIALIZERS
// =========================
window.addEventListener('load', () => {
    initAuth();
    bindEventListeners();
    showSection("VolunteerList"); // Call UI file to set default view
});

gapiLoaded();
gisLoaded();