// DOM Elements
const passwordModal = document.getElementById('password-modal');
const passwordForm = document.getElementById('password-form');
const passwordInput = document.getElementById('password-input');
const passwordError = document.getElementById('password-error');
const mainContent = document.getElementById('main-content');
const logoutBtn = document.getElementById('logout-btn');
const sermonForm = document.getElementById('sermon-form');
const notesInput = document.getElementById('notes');
const coverImageInput = document.getElementById('cover-image');
const fileName = document.getElementById('file-name');
const imagePreview = document.getElementById('image-preview');
const previewImg = document.getElementById('preview-img');
const clearImageBtn = document.getElementById('clear-image');
const submitBtn = document.getElementById('submit-btn');
const btnText = document.getElementById('btn-text');
const btnSpinner = document.getElementById('btn-spinner');
const result = document.getElementById('result');
const resultSuccess = document.getElementById('result-success');
const resultError = document.getElementById('result-error');
const downloadLink = document.getElementById('download-link');
const errorMessage = document.getElementById('error-message');
const commentaryMhc = document.getElementById('commentary-mhc');
const commentaryCalvin = document.getElementById('commentary-calvin');

// State
let coverImageBase64 = null;

// Check if already authenticated (has valid session cookie)
async function checkAuth() {
    try {
        // Try to access a protected endpoint
        const response = await fetch('/web/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ notes: '' }),
            credentials: 'include'
        });

        if (response.status !== 401) {
            // Already authenticated (even if request failed for other reasons)
            showMainContent();
            return;
        }
    } catch (e) {
        // Network error, show login
    }

    showPasswordModal();
}

function showPasswordModal() {
    passwordModal.classList.remove('hidden');
    mainContent.classList.add('hidden');
    passwordInput.focus();
}

function showMainContent() {
    passwordModal.classList.add('hidden');
    mainContent.classList.remove('hidden');
}

// Password Form Submit
passwordForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    passwordError.classList.add('hidden');

    const password = passwordInput.value;

    try {
        const response = await fetch('/web/auth', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password }),
            credentials: 'include'
        });

        const data = await response.json();

        if (data.valid) {
            showMainContent();
            passwordInput.value = '';
        } else {
            passwordError.classList.remove('hidden');
            passwordInput.select();
        }
    } catch (error) {
        passwordError.textContent = 'Connection error. Please try again.';
        passwordError.classList.remove('hidden');
    }
});

// Logout
logoutBtn.addEventListener('click', async () => {
    try {
        await fetch('/web/logout', {
            method: 'POST',
            credentials: 'include'
        });
    } catch (e) {
        // Ignore errors
    }

    coverImageBase64 = null;
    notesInput.value = '';
    commentaryMhc.checked = false;
    commentaryCalvin.checked = false;
    clearImagePreview();
    hideResults();
    showPasswordModal();
});

// File Input Handling
document.querySelector('.file-input-wrapper').addEventListener('click', () => {
    coverImageInput.click();
});

coverImageInput.addEventListener('change', async (e) => {
    const file = e.target.files[0];

    if (!file) {
        clearImagePreview();
        return;
    }

    // Update file name display
    fileName.textContent = file.name;

    // Read file as base64
    try {
        coverImageBase64 = await readFileAsBase64(file);

        // Show preview
        previewImg.src = URL.createObjectURL(file);
        imagePreview.classList.remove('hidden');
    } catch (error) {
        console.error('Failed to read file:', error);
        clearImagePreview();
    }
});

function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
            // Remove data URL prefix (e.g., "data:image/png;base64,")
            const base64 = reader.result.split(',')[1];
            resolve(base64);
        };
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

clearImageBtn.addEventListener('click', () => {
    clearImagePreview();
});

function clearImagePreview() {
    coverImageInput.value = '';
    fileName.textContent = 'No file chosen';
    imagePreview.classList.add('hidden');
    previewImg.src = '';
    coverImageBase64 = null;
}

// Form Submit
sermonForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    hideResults();

    const notes = notesInput.value.trim();

    if (!notes) {
        showError('Please enter sermon notes');
        return;
    }

    // Show loading state
    setLoading(true);

    // Collect selected commentaries (get elements fresh in case of DOM changes)
    const commentaries = [];
    const mhcCheckbox = document.getElementById('commentary-mhc');
    const calvinCheckbox = document.getElementById('commentary-calvin');
    console.log('MHC checkbox:', mhcCheckbox, 'checked:', mhcCheckbox?.checked);
    console.log('Calvin checkbox:', calvinCheckbox, 'checked:', calvinCheckbox?.checked);
    if (mhcCheckbox && mhcCheckbox.checked) commentaries.push(mhcCheckbox.value);
    if (calvinCheckbox && calvinCheckbox.checked) commentaries.push(calvinCheckbox.value);
    console.log('Commentaries to send:', commentaries);

    try {
        const response = await fetch('/web/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                notes: notes,
                image: coverImageBase64,
                commentaries: commentaries
            }),
            credentials: 'include'
        });

        if (response.status === 401) {
            showPasswordModal();
            return;
        }

        const data = await response.json();

        if (data.success && data.url) {
            showSuccess(data.url);
        } else {
            showError(data.error || 'Unknown error occurred');
        }
    } catch (error) {
        console.error('Request failed:', error);
        showError('Connection error. Please try again.');
    } finally {
        setLoading(false);
    }
});

function setLoading(loading) {
    submitBtn.disabled = loading;
    btnText.textContent = loading ? 'Generating...' : 'Generate PDF';
    btnSpinner.classList.toggle('hidden', !loading);
}

function hideResults() {
    result.classList.add('hidden');
    resultSuccess.classList.add('hidden');
    resultError.classList.add('hidden');
}

function showSuccess(url) {
    downloadLink.href = url;
    result.classList.remove('hidden');
    resultSuccess.classList.remove('hidden');
    resultError.classList.add('hidden');
}

function showError(message) {
    errorMessage.textContent = message;
    result.classList.remove('hidden');
    resultSuccess.classList.add('hidden');
    resultError.classList.remove('hidden');
}

// Initialize
checkAuth();
