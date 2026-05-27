// ==========================================
// ui.js - Handles DOM, UI Manipulations & Tabulator
// ==========================================

let volunteerTable;
let schoolTable;
let allocationTable;

let currentActiveSection = "VolunteerList"; // Default

// Global variables for timer management
let processStartTime;
let timerInterval;

// --- INITIALIZE UI COMPONENTS ---
window.addEventListener('DOMContentLoaded', () => {
    initTables();
});

function initTables() {
    // 1. Volunteer Table Configuration
    volunteerTable = new Tabulator("#dataTable", {
        data: [], 
        placeholder: "No Data Available",
        layout: "fitColumns",
        maxHeight: "550px",
        renderVertical: "basic",
        pagination: true,
        paginationMode: "local",
        paginationSize: 10,
        paginationSizeSelector: [10, 25, 50, 75, 100],
        movableColumns: false,
        resizableColumnFit: true,
        rowHeader:{formatter:function(cell){
        const table = cell.getTable();

        const page = table.getPage();
        const size = table.getPageSize();

        const pageIndex = page - 1;
        const rowIndex = cell.getRow().getPosition(false) - 1;

        return (pageIndex * size) + rowIndex + 1;
    }, title:"#", headerSort:false, hozAlign:"center", resizable:false, frozen:true, maxWidth:70},
        columns: [
            { 
                title: "Priority", field: "Priority", width: 120, 
                editor: "list", editorParams: { values: [1,2,3,4] }, 
                headerFilter: "list", headerFilterParams: { values: {"": "All", 1: "1", 2: "2", 3: "3", 4: "4"} }, resizable:false,
                // When a cell is edited in Tabulator, pass the change back to script.js
                cellEdited: function(cell) {
                    const rowData = cell.getRow().getData();
                    if (window.handlePriorityEdit) {
                        window.handlePriorityEdit(rowData.id, rowData.Priority);
                    }
                }
            },
            { title: "Name", field: "Name", mutateType: "data", // Tells Tabulator to run this on load
            mutator: function(value, data) {
                // Check all possible Excel column names
                return data.name || data.Name || data["Full Name"] || "Unknown";
            }, widthGrow: 2, headerFilter: "input" },
            { title: "Sector", field: "sector", widthGrow: 2, headerFilter: "input", maxWidth: 150 },
            { title: "Address", field: "address", widthGrow: 4, formatter: "textarea", variableHeight:true, headerFilter: "input" }
        ]
    });

    // 2. School Table Configuration
    schoolTable = new Tabulator("#dataTableSchool", {
        data: [],
        placeholder: "No Data Available",
        layout: "fitColumns",
        maxHeight: "550px",
        renderVertical: "basic",
        pagination: true,
        paginationMode: "local",
        paginationSize: 10,
        paginationSizeSelector: [10, 25, 50],
        movableColumns: false,
        resizableColumnFit: true,
        rowHeader:{formatter:function(cell){
        const table = cell.getTable();

        const page = table.getPage();
        const size = table.getPageSize();

        const pageIndex = page - 1;
        const rowIndex = cell.getRow().getPosition(false) - 1;

        return (pageIndex * size) + rowIndex + 1;
        }, title:"#", headerSort:false, hozAlign:"center", resizable:false, frozen:true, maxWidth:70},
        columns: [
            { title: "Name", field: "school_name", widthGrow: 2, headerFilter: "input" },
            { title: "Address", field: "address", widthGrow: 4, formatter: "textarea", variableHeight:true, headerFilter: "input" },
            { title: "Max Volunteer", field: "max volunteer", widthGrow: 2, headerFilter: "input", maxWidth: 180 },
            { title: "Area", field: "Planning Area", widthGrow: 1, formatter: "textarea", variableHeight:true, headerFilter: "input" }
        ]
    });

    // 3. Processed Allocation Table Configuration
    allocationTable = new Tabulator("#dataTableAllocation", {
        data: [],
        placeholder: "No Processed Data Yet",
        layout: "fitColumns",
        maxHeight: "550px",
        renderVertical: "basic",
        pagination: true,
        paginationMode: "local",
        paginationSize: 10,
        paginationSizeSelector: [10, 25, 50],
        columns: [
            // Adjust these fields based on what your backend actually returns
            { title: "Assigned School", field: "assigned_school", headerFilter: "input" },
            { title: "Max Volunteers", field: "Max Volunteers" },
            { title: "Volunteer Name", field: "name", headerFilter: "input" },
            { title: "Status", field: "status" }
        ]
    });

    window.loadAllocationDataToUI = function(schoolAssignments, parsedSchoolData) {
        if (allocationTable) {
            //totalvolunteersprocessed = schoolAssignments["summary_statistics"]["Total Assigned"] + schoolAssignments["summary_statistics"]["Total Unassigned"]
            //document.getElementById("finshedTotal").innerText = totalvolunteersprocessed;

            // // Run data transformer
            // const tableConfig = formatDynamicTableData(schoolAssignments, parsedSchoolData);

            // // Completely destroy old instance to prevent column definition overlap errors
            // if (window.allocationTable) {
            //     window.allocationTable.destroy();
            // }

            // // Render the dynamic structural layout inside Tabulator
            // window.allocationTable = new Tabulator("#dataTableAllocation", {
            //     data: tableConfig.data,           // Array of Objects
            //     columns: tableConfig.columns,     // Dynamic Header Array
            //     layout: "fitDataStandard",        // Automatically sizes wide columns neatly
            //     maxHeight: "550px",
            //     renderVertical: "basic",
            //     pagination: true,
            //     paginationMode: "local",
            //     paginationSize: 10,
            //     paginationSizeSelector: [10, 25, 50],
            // });
            
            // Automatically switch to the results tab so the user sees it
            //

            // 1. Debug line: check exactly what your AWS Python engine returned
            console.log("Raw backend data received:", schoolAssignments);

            let tableRows = [];

            // 2. Convert the nested dictionary/object into a flat array of row objects
            if (Array.isArray(schoolAssignments)) {
                // If it's already an array, use it directly
                tableRows = schoolAssignments;
            } else if (schoolAssignments && typeof schoolAssignments === 'object') {
                
                // Check if the array is hidden inside a property (e.g., schoolAssignments.allocations)
                if (Array.isArray(schoolAssignments.allocations)) {
                    tableRows = schoolAssignments.allocations;
                } else {
                    // It is a key-value dictionary (e.g., { "job_id_1": {...}, "job_id_2": {...} })
                    tableRows = Object.entries(schoolAssignments).map(([key, value]) => {
                        if (typeof value === 'object' && value !== null) {
                            return { id: key, ...value }; // Flattens the keys into rows
                        }
                        return { id: key, value: value };
                    });
                }
            }

            // 3. Pass the newly formatted flat array to Tabulator
            // Replace 'yourTabulatorInstance' with the actual variable name of your table (e.g., table, allocationTable)
            allocationTable.setData(tableRows);

            showSection("AllocationList"); 
        }
    };

    // Add this helper to toggle a loading spinner or disable buttons
    window.showProcessingStateUI = function(isProcessing, totalVolunteers = 0) {
        const processingDiv = document.getElementById("processingState");
        // Assuming you want to hide the main application container when processing
        const mainContent = document.getElementById("mainContentContainer"); 

        if (isVisible) {
            processingDiv.style.display = "block";
            if (mainContent) mainContent.style.display = "none";
            
            // Start the timer
            processStartTime = Date.now();
            timerInterval = setInterval(updateTimerDisplay, 1000);
            
            // Set the total
            document.querySelector(".progress_info p strong").textContent = `0 / ${totalVolunteers}`;
        } else {
            processingDiv.style.display = "none";
            if (mainContent) mainContent.style.display = "block";
            
            // Stop the timer
            clearInterval(timerInterval);
        }
    };
}

// 1. Toggles the Processing Screen and Timer
function toggleProcessingUI(isVisible) {
    const processingDiv = document.getElementById("processingState");
    const mainContent = document.getElementById("setupState");
    const finshDiv = document.getElementById("finishedState");

    if (isVisible) {
        // Show progress view, hide main view
        if (processingDiv) processingDiv.style.display = "block";
        if (mainContent) mainContent.style.display = "none";
        
        // Reset and Start Timer
        processStartTime = Date.now();
        document.querySelector(".timer_display").textContent = "00:00:00";
        timerInterval = setInterval(updateTimerDisplay, 1000);
        
        // Reset Progress Bar
        updateProgressUI(0, 0); 
    } else {
        // Hide progress view, show main view
        if (processingDiv) processingDiv.style.display = "none";
        if (finshDiv) finshDiv.style.display = "block";
        
        // Stop Timer
        clearInterval(timerInterval);
    }
}

// 2. Updates the text and the green bar fill
function updateProgressUI(processUser, totalUser) {
    // Avoid dividing by zero before data arrives
    const safeTotal = totalUser > 0 ? totalUser : 1; 
    const percent = Math.round((processUser / safeTotal) * 100);
    
    // Update Text (e.g., "45 / 133")
    const textElement = document.querySelector(".progress_info p strong");
    if (textElement) {
        textElement.textContent = `${processUser} / ${totalUser}`;
    }
    
    // Update Bar Width
    const barElement = document.querySelector(".progress_bar_fill");
    if (barElement) {
        barElement.style.width = `${percent}%`;
    }
}

// 3. Calculates elapsed time
function updateTimerDisplay() {
    const elapsed = Math.floor((Date.now() - processStartTime) / 1000);
    const hrs = String(Math.floor(elapsed / 3600)).padStart(2, '0');
    const mins = String(Math.floor((elapsed % 3600) / 60)).padStart(2, '0');
    const secs = String(elapsed % 60).padStart(2, '0');
    
    const timerElement = document.querySelector(".timer_display");
    if (timerElement) {
        timerElement.textContent = `${hrs}:${mins}:${secs}`;
    }
}

function formatDynamicTableData(schoolAssignments, parsedSchoolData) {
    let finalRows = [];
    let maxColsFound = 0;

    // 1. Iterate through each school received from AWS
    for (const [schoolName, volunteers] of Object.entries(schoolAssignments)) {
        
        // Safety check to ensure volunteers is an array
        if (!Array.isArray(volunteers)) continue;

        // Sort volunteers by travel time (lowest time first)
        volunteers.sort((a, b) => (a.time_sec || 0) - (b.time_sec || 0));

        // Dynamically track the max volunteer count to know how many columns to generate
        if (volunteers.length > maxColsFound) {
            maxColsFound = volunteers.length;
        }

        // Pull corresponding school info from your parsed frontend data with fallback defaults
        const schoolMeta = parsedSchoolData[schoolName];
        
        let rowData = {
            school: schoolName,
            max_vol: schoolMeta?.max ?? "N/A",  // Safely fallback if school isn't in Excel
            area: schoolMeta?.area ?? "N/A"     // Safely fallback if area is missing
        };

        // 2. Map every volunteer to flat properties (User 1, User 2...)
        volunteers.forEach((vol, index) => {
            let i = index + 1;
            let mins = Math.floor((vol.time_sec || 0) / 60);
            let secs = Math.floor((vol.time_sec || 0) % 60);

            rowData[`user_${i}`] = vol.user_data?.name ?? "Unknown";
            rowData[`travel_time_${i}`] = `${mins}m ${secs}s`;
            rowData[`minutes_${i}`] = ((vol.time_sec || 0) / 60).toFixed(2);
            rowData[`distance_${i}`] = vol.dist ?? 0;
        });

        finalRows.push(rowData);
    }

    // 3. Construct the dynamic Tabulator Columns definition
    let dynamicColumns = [
        { title: "School", field: "school", frozen: true, headerFilter: "input" }, 
        { title: "Max Volunteers", field: "max_vol", hozAlign: "center" },
        { title: "Area", field: "area", headerFilter: "list", headerFilterParams: { values: true } }
    ];

    // Build sub-column groups for each User slot dynamically
    for (let i = 1; i <= maxColsFound; i++) {
        dynamicColumns.push({
            title: `User ${i}`,
            columns: [
                { title: "Name", field: `user_${i}`, width: 120 },
                { title: "Travel Time", field: `travel_time_${i}`, hozAlign: "center" },
                { title: "Minutes", field: `minutes_${i}`, hozAlign: "center" },
                { title: "Distance (m)", field: `distance_${i}`, hozAlign: "right" }
            ]
        });
    }

    return { 
        data: finalRows, 
        columns: dynamicColumns 
    };
}

// --- DATA INGESTION FROM SCRIPT.JS ---
async function loadVolunteerDataToUI(data) {
    if (volunteerTable) {
        await volunteerTable.setData(data);

        volunteerTable.redraw(true);
        volunteerTable.setPage(1);
        updateSummary();
    }
}

async function loadSchoolDataToUI(data) {
    if (schoolTable) 
        {
            schoolTable.setData(data);

            schoolTable.redraw(true);
            schoolTable.setPage(1);
            updateSchoolSummary();
        }
}

// --- DASHBOARD SUMMARIES ---
function updateSummaryUI(parsedData) {
    let counts = { 1: 0, 2: 0, 3: 0, 4: 0 };
    
    parsedData.forEach(row => {
        if (counts[row['Priority']] !== undefined) counts[row['Priority']]++;
    });

    const elements = {
        "sumTotal": parsedData.length,
        "sumP1": counts[1],
        "sumP2": counts[2],
        "sumP3": counts[3],
        "sumP4": counts[4],
        "summaryTotal": parsedData.length,
        "summary1": counts[1],
        "summary2": counts[2],
        "summary3": counts[3],
        "summary4": counts[4]
    };

    for (const [id, value] of Object.entries(elements)) {
        const el = document.getElementById(id);
        if (el) el.innerText = value;
    }
}

function updateSchoolSummaryUI(parsedSchoolData, allocationData) {
    let totalSchool = 0;
    let openSlots = 0;
    
    parsedSchoolData.forEach(row => {
        totalSchool++;
        openSlots += (parseInt(row['max volunteer']) || 0);
    });

    if (document.getElementById("sumTotalSchool")) document.getElementById("sumTotalSchool").innerText = totalSchool;
    if (document.getElementById("massAssignSchoolTotal")) document.getElementById("massAssignSchoolTotal").innerText = totalSchool;

    if (!allocationData || allocationData.length === 0) {
        if (document.getElementById("schoolOpenSlots")) document.getElementById("schoolOpenSlots").innerText = openSlots;
        if (document.getElementById("sumS1")) document.getElementById("sumS1").innerText = 0;
        if (document.getElementById("sumS2")) document.getElementById("sumS2").innerText = totalSchool;
    }
}

// --- NAVIGATION & MODALS ---
function showSection(id, event) {
    document.querySelectorAll('.content_container').forEach(sec => sec.classList.remove('active'));
    document.getElementById(id).classList.add('active');
    document.querySelectorAll('.menu_btn').forEach(btn => btn.classList.remove('active'));
    if (event && event.target) {
        const btn = event.target.closest('.menu_btn');
        if (btn) btn.classList.add('active');
    }

    currentActiveSection = id;
}

function openModal() { document.getElementById("uploadModal").style.display = "flex"; }
function closeModal() { document.getElementById("uploadModal").style.display = "none"; }
function selectLocal() { document.getElementById("fileInput").click(); }

// --- AUTHENTICATION UI ---
function updateAuthUI(user, handleSignIn, handleSignOut) {
    const button = document.getElementById("signIn") || document.getElementById("signOut");
    const safeSetText = (id, text) => { if (document.getElementById(id)) document.getElementById(id).textContent = text; };

    if (user) {
        safeSetText("email", user.profile?.email || "");
        safeSetText("access-token", user.access_token || "");
        safeSetText("id-token", user.id_token || "");
        safeSetText("refresh-token", user.refresh_token || "");
         
        if (button) {
            button.textContent = "Log out";
            button.id = "signOut";
            button.removeEventListener("click", handleSignIn);
            button.addEventListener("click", handleSignOut);
        }
    } else {
        safeSetText("email", "");
        safeSetText("access-token", "");
        safeSetText("id-token", "");
        safeSetText("refresh-token", "");
            
        if (button) {
            button.textContent = "Sign In";
            button.id = "signIn";
            button.removeEventListener("click", handleSignOut);
            button.addEventListener("click", handleSignIn);
        }
    }
}

function test()
{
    console.log(volunteerTable.getPageSize());
}