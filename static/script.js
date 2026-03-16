document.addEventListener('DOMContentLoaded', function () {
    const btnMicToggle = document.getElementById('btn-mic-toggle');
    const txtTranscription = document.getElementById('transcription-text');
    const micStatusContainer = document.getElementById('mic-status-container');

    let recognition;
    let isRecording = false;

    function showError(msg) {
        if (micStatusContainer) {
            micStatusContainer.innerHTML = `<span style="color:red; font-weight:bold;">Error: ${msg}</span>`;
        } else {
            alert(msg);
        }
    }

    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = 'en-US';

        recognition.onstart = function () {
            isRecording = true;
            btnMicToggle.innerHTML = '<i class="fas fa-stop-circle" style="color:red;"></i> หยุดบันทึก (Stop)';
            btnMicToggle.style.backgroundColor = '#ffcccc';

            const boxMic = document.getElementById('box-mic');
            if (boxMic) {
                boxMic.innerText = "MIC ON (Say Stop)";
                boxMic.style.backgroundColor = "rgba(231, 76, 60, 0.8)";
            }

            if (micStatusContainer) micStatusContainer.innerText = 'กำลังฟัง... (Listening...)';
        };

        recognition.onend = function () {
            isRecording = false;
            btnMicToggle.innerHTML = '<i class="fas fa-microphone"></i> เริ่มบันทึกเสียง (Start)';
            btnMicToggle.style.backgroundColor = '#ddd';

            const boxMic = document.getElementById('box-mic');
            if (boxMic) {
                boxMic.innerText = "MIC OFF";
                boxMic.style.backgroundColor = "rgba(0, 0, 0, 0.5)";
                boxMic.style.border = "1px solid rgba(255, 255, 255, 0.3)";
            }
        };

        recognition.onresult = function (event) {
            let interimTranscript = '';
            let newFinalTranscript = '';

            for (let i = event.resultIndex; i < event.results.length; ++i) {
                if (event.results[i].isFinal) {
                    newFinalTranscript += event.results[i][0].transcript;
                } else {
                    interimTranscript += event.results[i][0].transcript;
                }
            }

            if (newFinalTranscript) {
                const active = document.activeElement;
                if (active && (active.tagName === 'TEXTAREA' || (active.tagName === 'INPUT' && active.type === 'text'))) {
                    if (active.value && !active.value.endsWith(' ')) {
                        active.value += ' ';
                    }
                    active.value += newFinalTranscript;
                    active.dispatchEvent(new Event('input', { bubbles: true }));
                } else {
                    if (txtTranscription) {
                        if (txtTranscription.value && !txtTranscription.value.endsWith(' ')) {
                            txtTranscription.value += ' ';
                        }
                        txtTranscription.value += newFinalTranscript;
                    }
                }
            }

            if (micStatusContainer) {
                if (interimTranscript) {
                    micStatusContainer.innerHTML = '<i class="fas fa-wave-square" style="color:red;"></i> กำลังฟัง: ' + interimTranscript;
                    micStatusContainer.style.color = '#888';
                }
            }
        };

        recognition.onerror = function (event) {
            isRecording = false;
            btnMicToggle.innerHTML = '<i class="fas fa-microphone"></i> เริ่มบันทึกเสียง (Start)';
            btnMicToggle.style.backgroundColor = '#ddd';

            if (event.error === 'not-allowed') {
                showError("ไม่อนุญาตให้ใช้ไมโครโฟน (Not Allowed). กรุณากด 'Allow' ที่แถบ URL หรือตรวจสอบการตั้งค่า");
            } else if (event.error === 'network') {
                showError("เกิดข้อผิดพลาดเครือข่าย (Network). ตรวจสอบอินเทอร์เน็ต หรือหากใช้ Chrome ปัญหาอาจเกิดจากการไม่ได้ใช้ HTTPS");
            } else if (event.error === 'no-speech') {
                if (micStatusContainer) micStatusContainer.innerText = "ไม่ได้รับเสียง (No Speech Detected)";
            } else {
                showError("ข้อผิดพลาด: " + event.error);
            }
        };

        btnMicToggle.addEventListener('click', function () {
            if (isRecording) {
                recognition.stop();
            } else {
                if (micStatusContainer) micStatusContainer.innerText = 'กำลังเริ่ม... (Starting...)';
                try {
                    recognition.start();
                } catch (e) {
                    showError("ไม่สามารถเริ่มไมค์ได้: " + e.message);
                }
            }
        });

    } else {
        btnMicToggle.style.display = 'none';
        showError("เบราว์เซอร์นี้ไม่รองรับ Web Speech API กรุณาใช้ Chrome หรือ Edge");
    }

    const videoElement = document.querySelector('.input_video');
    const canvasElement = document.querySelector('.output_canvas');
    let canvasCtx = null;

    if (!window.isSecureContext) {
        showError("Camera Error: App is NOT running in a Secure Context (HTTPS).");
    } else if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        showError("Camera Error: Browser API 'navigator.mediaDevices' is missing.");
    }

    if (canvasElement) {
        canvasCtx = canvasElement.getContext('2d');
    }

    let lastActionTime = 0;
    const ACTION_COOLDOWN = 800;

    function onResults(results) {
        if (!canvasCtx) return;

        canvasCtx.save();
        canvasCtx.translate(canvasElement.width, 0);
        canvasCtx.scale(-1, 1);
        canvasCtx.clearRect(0, 0, canvasElement.width, canvasElement.height);
        canvasCtx.drawImage(results.image, 0, 0, canvasElement.width, canvasElement.height);

        if (results.multiHandLandmarks) {
            for (const landmarks of results.multiHandLandmarks) {
                drawConnectors(canvasCtx, landmarks, HAND_CONNECTIONS, { color: '#00FF00', lineWidth: 2 });
                drawLandmarks(canvasCtx, landmarks, { color: '#FF0000', lineWidth: 1 });
                detectGesture(landmarks);
            }
        }
        canvasCtx.restore();
    }

    function detectGesture(landmarks) {
        const thumbTip = landmarks[4];
        const indexTip = landmarks[8];

        const distance = Math.sqrt(
            Math.pow(thumbTip.x - indexTip.x, 2) +
            Math.pow(thumbTip.y - indexTip.y, 2)
        );

        const cursorX_norm = 1 - ((thumbTip.x + indexTip.x) / 2);
        const cursorY_norm = (thumbTip.y + indexTip.y) / 2;

        const rect = canvasElement.getBoundingClientRect();
        const clientX = rect.left + (cursorX_norm * rect.width);
        const clientY = rect.top + (cursorY_norm * rect.height);

        const midX = (thumbTip.x + indexTip.x) / 2;
        const midY = (thumbTip.y + indexTip.y) / 2;

        const PINCH_THRESHOLD = 0.06;

        canvasCtx.beginPath();
        canvasCtx.arc(midX * canvasElement.width, midY * canvasElement.height, 5, 0, 2 * Math.PI);
        canvasCtx.fillStyle = distance < PINCH_THRESHOLD ? "rgba(0, 255, 0, 0.5)" : "rgba(255, 255, 255, 0.5)";
        canvasCtx.fill();

        if (distance < PINCH_THRESHOLD) {
            const element = document.elementFromPoint(clientX, clientY);

            if (element && element.classList.contains('gesture-box')) {
                element.classList.add('active');
                setTimeout(() => element.classList.remove('active'), 200);

                const now = Date.now();
                if (now - lastActionTime > ACTION_COOLDOWN) {
                    const action = element.getAttribute('data-action');
                    triggerAction(action);
                    lastActionTime = now;
                }
            }
        }
    }

    // --- อัปเดตฟังก์ชันเพื่อค้นหาช่องสี่เหลี่ยม/วงกลมโดยเฉพาะ ---
    function getVisual(el) {
        if (el.type === 'checkbox' || el.type === 'radio') {
            // ดึง element ตัวถัดไป (ซึ่งเราเขียน span จำลองสี่เหลี่ยมไว้ใน HTML)
            if (el.nextElementSibling) {
                return el.nextElementSibling;
            }
            return el.parentElement; // กรณีฉุกเฉิน
        }
        return el; // ถ้าเป็นช่อง Text ให้ล็อคที่ช่อง Text
    }

    function triggerAction(action) {
        switch (action) {
            case 'CLEAR':
                const activeElement = document.activeElement;
                if (activeElement) {
                    if (activeElement.type === 'text' || activeElement.tagName === 'TEXTAREA') {
                        activeElement.value = '';
                    }
                    else if (activeElement.type === 'checkbox' || activeElement.type === 'radio') {
                        activeElement.checked = false;
                        const parent = activeElement.parentElement;
                        if (parent && parent.classList.contains('circle-option')) {
                            const span = parent.querySelector('span');
                            if (span) span.style = "";
                        }
                    }
                    activeElement.classList.remove('low-confidence-highlight');
                    if (activeElement.nextElementSibling && activeElement.nextElementSibling.classList.contains('checkbox-visual')) {
                        activeElement.nextElementSibling.classList.remove('low-confidence-highlight');
                    }
                }
                break;
            case 'SCROLL_UP':
                document.querySelector('.document-pane').scrollBy({ top: -200, behavior: 'smooth' });
                break;
            case 'SCROLL_DOWN':
                document.querySelector('.document-pane').scrollBy({ top: 200, behavior: 'smooth' });
                break;
            case 'PREV':
                moveFocus(-1);
                break;
            case 'NEXT':
                moveFocus(1);
                break;
            case 'SELECT':
                const active = document.activeElement;
                if (active && (active.type === 'checkbox' || active.type === 'radio')) {
                    active.click();

                    // ให้วงกลมกระพริบที่กรอบสี่เหลี่ยม ไม่ใช่ครอบทั้งประโยค
                    const visualEl = getVisual(active);
                    if (visualEl) {
                        visualEl.classList.add('gesture-focus');
                        setTimeout(() => visualEl.classList.remove('gesture-focus'), 200);
                        setTimeout(() => visualEl.classList.add('gesture-focus'), 400);
                    }
                } else if (txtTranscription) {
                    txtTranscription.select();
                }
                break;
            case 'MIC_TOGGLE':
                const micBtn = document.getElementById('btn-mic-toggle');
                if (micBtn) micBtn.click();
                break;
            case 'SAVE':
                const downloadBtn = document.getElementById('btn-download-pdf');
                const saveBtn = document.getElementById('btn-save-submit');

                if (downloadBtn) {
                    window.location.href = downloadBtn.href;
                } else if (saveBtn) {
                    const form = saveBtn.closest('form');
                    if (form) form.submit();
                    else saveBtn.click();
                }
                break;
        }
    }

    function moveFocus(direction) {
        const inputs = Array.from(document.querySelectorAll('input[type="text"], textarea, input[type="checkbox"], input[type="radio"]'));
        const current = document.activeElement;
        const currentIndex = inputs.indexOf(current);

        // ถอด Focus เดิมออก
        if (current) {
            const currentVisual = getVisual(current);
            if (currentVisual) currentVisual.classList.remove('gesture-focus');
        }

        let nextIndex = 0;
        if (currentIndex !== -1) {
            nextIndex = currentIndex + direction;
        }

        if (nextIndex < 0) nextIndex = inputs.length - 1;
        if (nextIndex >= inputs.length) nextIndex = 0;

        if (nextIndex >= 0 && nextIndex < inputs.length) {
            const target = inputs[nextIndex];
            target.focus(); // โฟกัส Input ซ่อนไว้

            // ล็อคเป้ากรอบแดงไปที่กล่องสี่เหลี่ยม / วงกลม / Text
            const targetVisual = getVisual(target);
            if (targetVisual) {
                targetVisual.classList.add('gesture-focus');
                targetVisual.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }
    }

    if (typeof Hands !== 'undefined') {
        const hands = new Hands({
            locateFile: (file) => {
                return `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${file}`;
            }
        });

        hands.setOptions({
            maxNumHands: 1,
            modelComplexity: 1,
            minDetectionConfidence: 0.7,
            minTrackingConfidence: 0.7
        });

        hands.onResults(onResults);

        if (videoElement) {
            const camera = new Camera(videoElement, {
                onFrame: async () => {
                    await hands.send({ image: videoElement });
                },
                width: 480,
                height: 360
            });
            camera.start()
                .catch(err => {
                    const overlay = document.querySelector('.camera-overlay-text');
                    if (overlay) {
                        overlay.innerHTML = `<span style="color: red; font-weight: bold;">Camera Error: ${err.message || err.name}. Please allow camera access.</span>`;
                    }
                    showError("Camera Error: " + (err.message || err.name));
                });
        }
    } else {
        console.warn("MediaPipe Hands library not loaded.");
    }
});