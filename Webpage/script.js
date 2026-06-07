// ==========================================
// script.js - Core Logic, Auth, & AWS Integrations
// ==========================================

const CLIENT_ID = "1019972991546-q3ghh6j2lfad6udttk38gf1ef0f727li.apps.googleusercontent.com";
const API_KEY = "AIzaSyCX2BgN8yOJS20aURlr0BNXbz8tZ09VZs0";
const SCOPES = "https://www.googleapis.com/auth/drive.file";

//google global info
let accessToken = null;
let pickerInited = false;
let gisInited = false;
let tokenClient;
let userManager;
let driveState = {
    action: null,            // import | export
    accessToken: null,

    currentFolder: "root",
    stack: [],
    nextPageToken: null,

    sort: "name",            // name | modifiedTime | mimeType
    search: {
        text: "",
        scope: "folder" // "folder" | "drive"
    },
    sortOrder: "name asc",

    selected: null,

    sharedDrives: [],
    treeCache: {},            // folder tree cache
    tree: {
        expanded: {},   // folderId → true/false
        children: {}    // folderId → [folders]
    }
};

// Source of Truth Data Arrays
let parsedData = []; //volunteer data
let parsedSchoolData = []; // school data
let allocationData = []; //processed data

let currentPage = 1;
let rowsPerPage = 50;

const DEFAULT_CACHE_KEY1 = "volunteer_data";
const DEFAULT_CACHE_KEY2 = "school_data";
const DEFAULT_CACHE_KEY3 = "allocation_data";

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

function getFileIcon(file) {
  const mime = file.mimeType || "";
  const name = file.name || "";

  // Folder (Windows folder icon)
  if (mime === "application/vnd.google-apps.folder") {
    return "icon-folder";
  }

  // Excel
  if (
    mime === "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" ||
    mime === "application/vnd.ms-excel" ||
    name.endsWith(".xlsx") ||
    name.endsWith(".xls")
  ) {
    return "icon-excel";
  }

  // JSON
  if (mime === "application/json" || name.endsWith(".json")) {
    return "icon-json";
  }

  // PDF
  if (mime === "application/pdf" || name.endsWith(".pdf")) {
    return "icon-pdf";
  }

  return "icon-file";
}


/**
 * Dynamically resolves file configurations depending on the user's active viewport page.
 * Maps back to currentActiveSection inside your UI controllers.
 */
function getCurrentPageConfig() {
    const activeSection = window.currentActiveSection || "VolunteerList"; 
    
    const registry = {
        "VolunteerList": {
            section: activeSection,
            cacheKey: DEFAULT_CACHE_KEY1,
            defaultFileName: "Processed_Vol_Data"
        },
        "SchoolList": {
            section: activeSection, 
            cacheKey: DEFAULT_CACHE_KEY2,
            defaultFileName: "Processed_School_List"
        },
        "AllocationList": {
            section: activeSection,
            cacheKey: DEFAULT_CACHE_KEY3,
            defaultFileName: "School_Allocation"
        }
    };

    return registry[activeSection] || registry["VolunteerList"];
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
// =========================
// NEW FILE SYSTEM
// =========================
/**
 * Unified Export Router Engine.
 * Always targets browser session cache arrays first, applying structural column flatteners.
 * @param {string} storageTarget - Choose 'local' for desktop downloads or 'gdrive' for cloud storage.
 */
async function triggerFileExport(storageTarget) {
    executeExcelExportWorkflow(storageTarget);
}

/**
 * Master Export Engine. 
 * Checks the current active section, formats the corresponding data, and triggers the export.
 */
async function executeExcelExportWorkflow(destination, folderId = null) {
    // 1. Determine which page the user is currently looking at
    const {section, cacheKey, defaultFileName} = getCurrentPageConfig();
    const workbook = XLSX.utils.book_new(); // Create a new blank Excel workbook

    try {
        switch (section) {
            
            // ==========================================
            // ROUTE 1: VOLUNTEER LIST (Flat Data)
            // ==========================================
            case "VolunteerList":
                if (!parsedData || parsedData.length === 0) {
                    return alert("No Volunteer data available to export.");
                }
                
                // Map to a clean object to strip out internal Tabulator 'id' fields
                const cleanVolunteers = parsedData.map(v => ({
                    "Priority": v.Priority,
                    "Name": v.Name,
                    "Sector": v.Sector,
                    "Address": v.Address
                }));
                
                const volSheet = XLSX.utils.json_to_sheet(cleanVolunteers);
                XLSX.utils.book_append_sheet(workbook, volSheet, "Volunteers");
                break;

            // ==========================================
            // ROUTE 2: SCHOOL LIST (Flat Data)
            // ==========================================
            case "SchoolList":
                if (!parsedSchoolData || parsedSchoolData.length === 0) {
                    return alert("No School data available to export.");
                }
                
                const cleanSchools = parsedSchoolData.map(s => ({
                    "School Name": s.SchoolName,
                    "Planning Area": s["Planning Area"],
                    "Max Capacity": s["max volunteer"],
                    "Address": s.Address,
                    "Latitude": s.Latitude,
                    "Longitude": s.Longitude
                }));
                
                const schoolSheet = XLSX.utils.json_to_sheet(cleanSchools);
                XLSX.utils.book_append_sheet(workbook, schoolSheet, "Schools");
                break;

            // ==========================================
            // ROUTE 3: ALLOCATION LIST (Deep Nested Data)
            // ==========================================
            case "AllocationList":
                if (!allocationData || !allocationData.assignments) {
                    return alert("No Allocation data available to export. Please process data first.");
                }
                const allocData = allocationData;

                // --- TAB 1: FLATTENED ASSIGNMENTS ---
                const flatAssignments = [];
                
                // Loop through the dictionary of schools: { "School A": {...}, "School B": {...} }
                for (const [schoolName, schoolInfo] of Object.entries(allocData.assignments)) {
                    
                    const baseSchoolRow = {
                        "School Name": schoolName,
                        "Area": schoolInfo["Area"],
                        "Max Capacity": schoolInfo["Max Volunteers"]
                    };

                    // Extract all keys that start with "User " (e.g., "User 1", "User 2")
                    const userKeys = Object.keys(schoolInfo).filter(k => k.startsWith("User "));

                    if (userKeys.length === 0) {
                        // Edge Case: School exists but has no volunteers
                        flatAssignments.push({
                            ...baseSchoolRow,
                            "Volunteer Name": "No Volunteers Assigned",
                            "Travel Time": "",
                            "Total Minutes": "",
                            "Distance (m)": ""
                        });
                    } else {
                        // Spread each user into their own flat row alongside the school data
                        userKeys.forEach(userKey => {
                            const user = schoolInfo[userKey];
                            flatAssignments.push({
                                ...baseSchoolRow,
                                "Volunteer Name": user["Name"],
                                "Travel Time": user["Travel Time"],
                                "Total Minutes": user["Total Minutes"],
                                "Distance (m)": user["Distance (meters)"]
                            });
                        });
                    }
                }
                const assignSheet = XLSX.utils.json_to_sheet(flatAssignments);
                XLSX.utils.book_append_sheet(workbook, assignSheet, "Assigned Volunteers");

                // --- TAB 2: UNASSIGNED USERS ---
                if (allocData.unassigned_users && allocData.unassigned_users.length > 0) {
                    const unassignedSheet = XLSX.utils.json_to_sheet(allocData.unassigned_users);
                    XLSX.utils.book_append_sheet(workbook, unassignedSheet, "Unassigned Users");
                }

                // --- TAB 3: SUMMARY STATISTICS ---
                if (allocData.summary_statistics) {
                    // Convert the summary dictionary into a clean 2-column key-value array
                    const summaryArray = Object.entries(allocData.summary_statistics).map(([statName, statValue]) => ({
                        "Statistic": statName,
                        "Value": statValue
                    }));
                    const summarySheet = XLSX.utils.json_to_sheet(summaryArray);
                    XLSX.utils.book_append_sheet(workbook, summarySheet, "Summary Report");
                }
                break;
                
            default:
                return alert("Export is not supported on this page.");
        }

        // ==========================================
        // FINAL ROUTING: LOCAL VS GOOGLE DRIVE
        // ==========================================
        // Assumes you are using the State-Driven mode (Method 1) we discussed earlier
        if (destination === 'gdrive') {
            // Passes the workbook and the Folder ID grabbed from the picker
            await saveExcelToGoogleDrive(workbook, defaultFileName, folderId);
        } 
        else if (destination === 'local') {
            // Triggers the local OS folder selector
            await saveExcelLocally(workbook, defaultFileName);
        }

    } catch (error) {
        console.error("Export Engine Failure:", error);
        alert(`Failed to export data: ${error.message}`);
    }
}

/**
 * Triggers native OS file picker to let user choose where to save the Excel file
 */
async function saveExcelLocally(workbook, defaultFileName) {
    try {
        // Convert the SheetJS workbook into a binary array block
        const excelBuffer = XLSX.write(workbook, { bookType: 'xlsx', type: 'array' });
        const excelBlob = new Blob([excelBuffer], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });

        // Check if the browser supports the modern File System Access API (Chrome/Edge)
        if (window.showSaveFilePicker) {
            const fileHandle = await window.showSaveFilePicker({
                suggestedName: `${defaultFileName}.xlsx`,
                types: [{
                    description: 'Excel Spreadsheet',
                    accept: { 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'] }
                }]
            });

            // Open a stream to write straight to that user-selected folder
            const writableStream = await fileHandle.createWritable();
            await writableStream.write(excelBlob);
            await writableStream.close();
            
            console.log("File successfully exported to user designated folder.");
        } else {
            // Fallback for Firefox/Safari which don't support showSaveFilePicker yet
            XLSX.writeFile(workbook, `${defaultFileName}.xlsx`);
        }
    } catch (err) {
        // Catches instances where user clicks 'Cancel' on the directory selector box
        if (err.name !== 'AbortError') {
            console.error("Local Save Error:", err);
            alert("Failed to save file locally.");
        }
    }
}

/**
 * Streams SheetJS generated excel workbook directly into the chosen Google Drive folder
 */
async function saveExcelToGoogleDrive(workbook, filename, targetFolderId) {
    if (!accessToken) return alert("Google Drive authentication missing.");
    
    // Convert workbook to a binary blob
    const excelBuffer = XLSX.write(workbook, { bookType: 'xlsx', type: 'array' });
    const fileBlob = new Blob([excelBuffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    
    // Metadata now includes 'parents' to place it in the selected folder
    const metadata = {
        name: `${filename}.xlsx`,
        mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        parents: [targetFolderId] 
    };
    
    const uploadForm = new FormData();
    uploadForm.append('metadata', new Blob([JSON.stringify(metadata)], { type: 'application/json' }));
    uploadForm.append('file', fileBlob);
    
    try {
        const response = await fetch('https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart', {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${accessToken}` },
            body: uploadForm
        });
        
        if (!response.ok) {
            const errorText = await response.text();

            console.error("Drive API Error:", errorText);

            throw new Error(
                `Google Drive upload failed (${response.status}): ${errorText}`
            );
        }
        alert("🎉 Successfully saved Excel file to your selected Google Drive folder!");
        
    } catch (error) {
        console.error("Drive Export Error:", error);
        alert(`Failed to save to Drive: ${error.message}`);
    }
}

// =========================
// FILE PROCESSING (EXCEL TO JSON)
// =========================
function bindEventListeners() {
    document.getElementById("fileInput")?.addEventListener("change", function(e) {
        const file = e.target.files[0];
        if (file) processUploadedFile(file);
        e.target.value = ""; // Reset the input so the user can upload the same file again if needed
    });
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
                if (storeCache(DEFAULT_CACHE_KEY1, parsedData))
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
                    "Planning Area": row['Area'] || row['area'] || row['Planning Area'] ||'',
                    "Latitude": row['Latitude'] || '',
                    "Longitude": row['Longitude'] ||''
                };
            });;
            
            loadSchoolDataToUI(parsedSchoolData); 
            //updateSchoolSummary();
            if (user && user.id_token) {
                uploadToLambda(parsedSchoolData, "schools.json");
            }
            else { //Guest save to cache
                storeCache(DEFAULT_CACHE_KEY2, parsedSchoolData);
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
            if (response.error) throw response;

            driveState.accessToken = response.access_token;
            accessToken = response.access_token;
            
            document.getElementById("driveModal").classList.remove("hidden");
            openFolder("root");
            initTree();
            loadSharedDrives();
        }
    });
    gisInited = true;
}

function selectGoogleDrive(action) {
    driveState.action = action;
    driveState.currentFolder = "root";
    driveState.stack = [];
    driveState.selected = null;

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
        document.getElementById("driveModal").classList.remove("hidden");
        openFolder("root");
        initTree();
        loadSharedDrives();
    }
}

function buildQuery(folderId) {
    let base =
        folderId === "root"
        ? "'root' in parents and trashed=false"
        : `'${folderId}' in parents and trashed=false`;

    // ❌ WRONG: filtering removes folders
    // base += " and mimeType='excel'"

    // ✅ CORRECT: only filter files, NOT folders
    if (driveState.action === "import") {
        base +=
        " and (mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' " +
        "or mimeType='application/vnd.ms-excel' " +
        "or mimeType='application/vnd.google-apps.folder')";
    }

    if (driveState.search.text) {

        if (driveState.search.scope === "drive") {
            base = "trashed=false"; // override folder restriction
        }

        base += ` and name contains '${driveState.search.text}'`;
    }

  return base;
}

async function listFiles(folderId, pageToken = null) {
    const query = buildQuery(folderId);

    let url =
        `https://www.googleapis.com/drive/v3/files` +
        `?q=${encodeURIComponent(query)}` +
        `&fields=nextPageToken,files(id,name,mimeType,modifiedTime)` +
        `&pageSize=50` +
        `&orderBy=${driveState.sortOrder}` +
        `&supportsAllDrives=true` +
        `&includeItemsFromAllDrives=true`;

    if (pageToken) url += `&pageToken=${pageToken}`;

    const res = await fetch(url, {
        headers: {
        Authorization: `Bearer ${driveState.accessToken}`
        }
    });

    const data = await res.json();

    driveState.nextPageToken = data.nextPageToken || null;

    return data.files || [];
}

async function loadMore() {
    if (!driveState.nextPageToken) return;

    const more = await listFiles(
        driveState.currentFolder,
        driveState.nextPageToken
    );

    renderFiles(more, true);

    // IMPORTANT: state already updated inside listFiles()
    updateLoadMoreButton();
}

function updateLoadMoreButton() {
    const btn = document.getElementById("loadMoreBtn");

    if (!btn) return;

    if (driveState.nextPageToken) {
        btn.style.display = "block";
    } else {
        btn.style.display = "none";
    }
}

function onSearch(value) {
    driveState.search.text = value;
    openFolder(driveState.currentFolder);
}

function setSearchScope(scope) {
  driveState.search.scope = scope;

  // 🔥 AUTO RE-SEARCH USING CURRENT TEXT
  const currentText = document.getElementById("searchBox").value;

  driveState.search.text = currentText;

  openFolder(driveState.currentFolder);
}

async function openFolder(folderId, folderName = "Folder", navType = "push") {
    // 🧠 ROOT RESET
    if (folderId === "root") {
        driveState.stack = [{ id: "root", name: "My Drive" }];
    }

    // 🧠 BREADCRUMB NAVIGATION (truncate stack)
    else if (navType === "breadcrumb") {
        const index = driveState.stack.findIndex(f => f.id === folderId);
        if (index !== -1) {
        driveState.stack = driveState.stack.slice(0, index + 1);
        }
    }

    // 🧠 TREE NAVIGATION (replace current, DO NOT push)
    else if (navType === "tree") {
        const existing = driveState.stack.find(f => f.id === folderId);

        driveState.stack = existing
        ? driveState.stack.slice(0, driveState.stack.indexOf(existing) + 1)
        : [{ id: "root", name: "My Drive" }, { id: folderId, name: folderName }];
    }

    // 🧠 NORMAL CLICK (push)
    else {
        const last = driveState.stack[driveState.stack.length - 1];
        if (!last || last.id !== folderId) {
        driveState.stack.push({ id: folderId, name: folderName });
        }
    }

    driveState.currentFolder = folderId;
    driveState.nextPageToken = null;

    const files = await listFiles(folderId);

    renderFiles(files, false);
    renderFolderTree(folderId);
    renderBreadcrumbs();

    // 🔥 IMPORTANT
    updateLoadMoreButton();
}

function renderFiles(files, append = false) {
    const container = document.getElementById("fileList");

    if (!files || files.length === 0) {
        container.innerHTML = `
            <div style="padding:12px;color:#888;">
            This folder is empty
            </div>
        `;
        return;
    }

    if (!append) container.innerHTML = "";

    files.forEach(f => {
        const isFolder = f.mimeType === "application/vnd.google-apps.folder";

        const row = document.createElement("div");
        row.className = "row";

        const iconClass = getFileIcon(f);

        row.innerHTML = `
        <span class="file-icon ${iconClass}"></span>
        <span class="name">${f.name}</span>
        <span class="meta">${f.modifiedTime || ""}</span>
        `;

        if (driveState.currentFolder === f.id) {
        row.classList.add("selected");
        }

        row.onclick = () => {
        if (isFolder) {
            openFolder(f.id, f.name, false);
        } else {
            driveState.selected = f;
        }
        };

        container.appendChild(row);
    });
}

async function toggleFolder(folderId) {

  // collapse
  if (driveState.tree.expanded[folderId]) {
    driveState.tree.expanded[folderId] = false;
    renderTree();
    return;
  }

  // expand + lazy load
  if (!driveState.tree.children[folderId]) {
    driveState.tree.children[folderId] = await fetchChildren(folderId);
  }

  driveState.tree.expanded[folderId] = true;
  renderTree();
}

async function renderFolderTree() {
    if (driveState.treeCache.root) {
        sidebar.innerHTML = driveState.treeCache.root;
        return;
    }
    const sidebar = document.getElementById("tree");

    const res = await fetch(
        `https://www.googleapis.com/drive/v3/files?q='root' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false&fields=files(id,name)`,
        {
        headers: {
            Authorization: `Bearer ${driveState.accessToken}`
        }
        }
    );

    const data = await res.json();

    let html = `
        <div onclick="openFolder('root','My Drive','breadcrumb')">
        🏠 My Drive
        </div>
    `;

    html += data.files.map(f =>
        `<div class="tree-item"
            onclick="openFolder('${f.id}','${f.name}','tree')">
            📁 ${f.name}
        </div>`
    ).join("");

    sidebar.innerHTML = html;
}

async function fetchChildren(folderId) {
  const res = await fetch(
    `https://www.googleapis.com/drive/v3/files?q='${folderId}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false&fields=files(id,name)`,
    {
      headers: {
        Authorization: `Bearer ${driveState.accessToken}`
      }
    }
  );

  const data = await res.json();
  return data.files || [];
}

function renderTree() {
  const sidebar = document.getElementById("tree");

  const root = driveState.tree.children["root"] || [];

  let html = `
    <div class="tree-item" onclick="openFolder('root','My Drive')">
      🏠 My Drive
    </div>
  `;

  html += renderTreeNodes("root", root, 0);

  sidebar.innerHTML = html;
}

function renderTreeNodes(parentId, nodes, level) {
  let html = "";

  nodes.forEach(f => {
    const isExpanded = driveState.tree.expanded[f.id];

    html += `
      <div class="tree-item" style="padding-left:${level * 16}px">
        
        <span onclick="toggleFolder('${f.id}')">
          ${isExpanded ? "📂" : "📁"}
        </span>

        <span onclick="openFolder('${f.id}','${f.name}','tree')">
          ${f.name}
        </span>
      </div>
    `;

    // render children if expanded
    if (isExpanded && driveState.tree.children[f.id]) {
      html += renderTreeNodes(
        f.id,
        driveState.tree.children[f.id],
        level + 1
      );
    }
  });

  return html;
}

async function initTree() {
  driveState.tree.children["root"] = await fetchChildren("root");
  renderTree();
}

async function loadSharedDrives() {
    const res = await fetch(
        "https://www.googleapis.com/drive/v3/drives?pageSize=100",
        {
            headers: {
                Authorization: `Bearer ${driveState.accessToken}`
            }
        }
    );

    const data = await res.json();

    //console.log("Shared drives response:", data); // 🔥 DEBUG

    const el = document.getElementById("sharedDrives");

    if (!data.drives || data.drives.length === 0) {
        el.innerHTML = `<div style="padding:8px;color:#888;">No shared drives</div>`;
        return;
    }

    el.innerHTML = data.drives.map(d =>
        `<div class="tree-item"
            onclick="openSharedDrive('${d.id}')">
            🗂 ${d.name}
        </div>`
    ).join("");
}

function openSharedDrive(id) {
  openFolder(id);
}

function setSort(type) {
    const orderMap = {
        name: "name asc",
        date: "modifiedTime desc",
        type: "mimeType asc"
    };
    driveState.sort = type;
    driveState.sortOrder = orderMap[type];
    openFolder(driveState.currentFolder);
}

function confirmSelection() {
  if (driveState.action === "export") {
    executeExcelExportWorkflow("gdrive", driveState.currentFolder);
  }

  if (driveState.action === "import") {
    if (!driveState.selected) return alert("Select a file first");
    downloadDriveFile(
      driveState.selected.id,
      driveState.selected.name
    );
  }

  closeDrive();
}

function goRoot() {
    openFolder("root");
    driveState.stack = [
        { id: "root", name: "My Drive" }
    ];
}

function goBack() {
  const prev = driveState.stack.pop();
  if (prev) openFolder(prev);
}

function renderBreadcrumbs() {
  const el = document.getElementById("breadcrumbs");

  el.innerHTML = driveState.stack.map((f, index) => {
    return `<span onclick="openFolder('${f.id}','${f.name}','breadcrumb')">
              ${f.name}
            </span>`;
  }).join(" / ");
}

function closeDrive() {
  document.getElementById("driveModal").classList.add("hidden");
}

//old stuff from here onwards
async function selectFile(fileId, fileName) {
    const response = await fetch(
        `https://www.googleapis.com/drive/v3/files/${fileId}?alt=media`,
        {
            headers: {
                Authorization: `Bearer ${accessToken}`
            }
        }
    );

    const file = new File([await response.blob()], fileName);
    processUploadedFile(file);
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
// AWS LAMBDA / FILE UPLOAD (This is only for signed in user)
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
                const CACHE_KEY1 = `${userId}_${DEFAULT_CACHE_KEY1}}`;
                parsedData = processedData;
                storeCache(CACHE_KEY1, parsedData);
                loadVolunteerDataToUI(parsedData);
            } else if (filename === "schools.json") {
                console.info(`fetching ${filename} data from AWS!`);
                const CACHE_KEY2 = `${userId}_${DEFAULT_CACHE_KEY2}}`;
                parsedSchoolData = processedData;
                storeCache(CACHE_KEY2, parsedSchoolData);
                loadSchoolDataToUI(parsedSchoolData);
            } else {
                console.info(`fetching ${filename} data from AWS!`);
                const CACHE_KEY3 = `${userId}_${DEFAULT_CACHE_KEY3}}`;
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

            parsedData = getCache(DEFAULT_CACHE_KEY1);
            parsedSchoolData = getCache(DEFAULT_CACHE_KEY2);
            allocationData = getCache(DEFAULT_CACHE_KEY3);

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

            const CACHE_KEY1 = `${userId}_${DEFAULT_CACHE_KEY1}]`;
            const CACHE_KEY2 = `${userId}_${DEFAULT_CACHE_KEY2}}`;
            const CACHE_KEY3 = `${userId}_${DEFAULT_CACHE_KEY3}}`;

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

// =================================
// batch processing JSON Merging
// =================================
const mergeRules = {
    summary_statistics: {
        "Total Assigned": "add",
        "Total Unassigned": "add",
        "Total School": "add",
        "Schools Filled": "add",
        "Total slot left": "subtract",
        "Priority 1 left": "subtract",
        "Priority 2 left": "subtract",
        "Priority 3 left": "subtract",
        "Priority 4 left": "subtract"
    }
};

function mergeWithRules(target, source) {

    for (const key in source) {
        const value = source[key];

        // arrays → concat
        if (Array.isArray(value)) {
            target[key] = (target[key] || []).concat(value);
            continue;
        }

        // objects → special case (summary_statistics or deep object)
        if (typeof value === "object" && value !== null) {

            // handle summary_statistics with math rules
            if (key === "summary_statistics") {

                target[key] = target[key] || {};

                for (const statKey in value) {

                    const rule = mergeRules.summary_statistics?.[statKey] || "add";

                    const current = Number(target[key][statKey] || 0);
                    const incoming = value.hasOwnProperty(statKey) ? value[statKey] : null;

                    if (incoming === null) continue;

                    if (rule === "add") {
                        target[key][statKey] = current + incoming;
                    }

                    if (rule === "subtract") {
                        target[key][statKey] = current - incoming;
                    }
                }

                continue;
            }

            // default deep merge for other objects
            target[key] = mergeWithRules(target[key] || {}, value);
            continue;
        }

        // primitive overwrite
        target[key] = value;
    }

    return target;
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

        let waveResults = {};
        

        let finalProcessedData = null;

        const BATCH_SIZE = 20; 
        const CONCURRENT_WAVES = 3; // How many batches to process at the exact same time
            
        let completedCount = 0;
        const defaultState = {
            assignments: {},
            unassigned_users: [],
            summary_statistics: {
                "Total Assigned": 0,
                "Total Unassigned": 0,
                "Total School": 0,
                "Schools Filled": 0,
                "Total slot left": 0,
                "Priority 1 left": 0,
                "Priority 2 left": 0,
                "Priority 3 left": 0,
                "Priority 4 left": 0
            }
        };

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

            updateProgressUI(0,total);

            // 2. Pre-slice all the data into an array of batches
            const allBatches = [];
            for (let i = 0; i < total; i += BATCH_SIZE) {
                allBatches.push(parsedData.slice(i, i + BATCH_SIZE));
            }

            console.log(`Prepared ${allBatches.length} total batches. Processing ${CONCURRENT_WAVES} at a time...`);

            // 3. The Concurrent Wave Engine
            for (let i = 0; i < allBatches.length; i += CONCURRENT_WAVES) {
                // Grab the next 3 batches
                const currentWaveBatches = allBatches.slice(i, i + CONCURRENT_WAVES);
                
                // Create an array of Promises (these execute simultaneously!)
                const wavePromises = currentWaveBatches.map(async (batch, index) => {
                    const response = await fetch(lambdaFunctionURL, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            action: "process_guest",
                            user_data: batch,
                            school_data: parsedSchoolData 
                        })
                    });

                    if (!response.ok) throw new Error(`Batch failed: ${response.statusText}`);

                    const responseData = await response.json();
                    let processedChunk = responseData.processed_json || responseData;
                    if (typeof processedChunk === "string") processedChunk = JSON.parse(processedChunk);

                    // 🎉 INSTANT UI UPDATE: As soon as THIS specific batch finishes, update the bar
                    completedCount += batch.length;
                    updateProgressUI(completedCount, total);

                    return processedChunk;
                });

                // Wait for all 3 batches in this specific wave to finish before moving on
                waveResults = await Promise.all(wavePromises);
                console.log("current result: ", waveResults);

                
            }

            const final = waveResults.reduce((acc, chunk) => {
                if (!chunk) return acc;
                return mergeWithRules(acc, chunk);
            }, structuredClone(defaultState));

            // 4. Final UI Update
            console.log("All concurrent waves complete!");

            // if (window.loadAllocationDataToUI) {
            //     const schoolInfo = window.parsedSchoolData || {};
            //     window.loadAllocationDataToUI(finalMasterArray, schoolInfo);
            // }
        
            //toggleProcessingUI("finished", finalMasterArray);
            
            


            // const response = await fetch(lambdaFunctionURL, {
            //     method: "POST",
            //     headers: { "Content-Type": "application/json" },
            //     body: JSON.stringify({
            //         action: "process_guest",
            //         user_data: parsedData,          // Volunteer arrays
            //         school_data: parsedSchoolData   // School arrays
            //     })
            // });

            // if (!response.ok) throw new Error("Guest processing failed or timed out.");

            // const resultData = await response.json();
            let parsedResponse = typeof final === "string" ? JSON.parse(final) : final;
            
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
                console.log("Guest Processing complete! Updating Allocation Table...");
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