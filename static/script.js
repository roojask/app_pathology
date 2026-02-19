document.addEventListener('DOMContentLoaded', function () {
    const btnMicToggle = document.getElementById('btn-mic-toggle');
    const txtTranscription = document.getElementById('transcription-text');
    const micStatusContainer = document.getElementById('mic-status-container');

    let recognition;
    let isRecording = false;

    // Helper to log errors to UI
    function showError(msg) {
        if (micStatusContainer) {
            micStatusContainer.innerHTML = `<span style="color:red; font-weight:bold;">Error: ${msg}</span>`;
        } else {
            alert(msg);
        }
    }

    // Check for Web Speech API Support
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

            // Sync Gesture Box
            const boxMic = document.getElementById('box-mic');
            if (boxMic) {
                boxMic.innerText = "MIC ON (Say Stop)";
                boxMic.style.backgroundColor = "rgba(231, 76, 60, 0.8)"; // Red
            }

            if (micStatusContainer) micStatusContainer.innerText = 'กำลังฟัง... (Listening...)';
            console.log("Microphone started");
        };

        recognition.onend = function () {
            isRecording = false;
            btnMicToggle.innerHTML = '<i class="fas fa-microphone"></i> เริ่มบันทึกเสียง (Start)';
            btnMicToggle.style.backgroundColor = '#ddd';

            // Sync Gesture Box
            const boxMic = document.getElementById('box-mic');
            if (boxMic) {
                boxMic.innerText = "MIC OFF";
                boxMic.style.backgroundColor = "rgba(0, 0, 0, 0.5)"; // Default
                boxMic.style.border = "1px solid rgba(255, 255, 255, 0.3)";
            }

            console.log("Microphone stopped");

            // Only clear if no error message was shown recently? 
            // Better to just leave it empty or show "Ready".
            // if (micStatusContainer) micStatusContainer.innerText = '';
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
                // Check for focused element
                const active = document.activeElement;
                if (active && (active.tagName === 'TEXTAREA' || (active.tagName === 'INPUT' && active.type === 'text'))) {
                    // Append to focused input
                    if (active.value && !active.value.endsWith(' ')) {
                        active.value += ' ';
                    }
                    active.value += newFinalTranscript;
                    // Dispatch input event for any listeners
                    active.dispatchEvent(new Event('input', { bubbles: true }));
                } else {
                    // Default: specific transcription box
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
                } else {
                    // Start clearing it if silence?
                    // micStatusContainer.innerText = ''; 
                }
            }
        };

        recognition.onerror = function (event) {
            console.error("Speech Recognition Error", event.error);
            isRecording = false;
            btnMicToggle.innerHTML = '<i class="fas fa-microphone"></i> เริ่มบันทึกเสียง (Start)';
            btnMicToggle.style.backgroundColor = '#ddd';

            if (event.error === 'not-allowed') {
                showError("ไม่อนุญาตให้ใช้ไมโครโฟน (Not Allowed). กรุณากด 'Allow' ที่แถบ URL หรือตรวจสอบการตั้งค่า");
            } else if (event.error === 'network') {
                showError("เกิดข้อผิดพลาดเครือข่าย (Network). ตรวจสอบอินเทอร์เน็ต หรือหากใช้ Chrome ปัญหาอาจเกิดจากการไม่ได้ใช้ HTTPS");
            } else if (event.error === 'no-speech') {
                // Ignore often, just means silence
                // showError("ไม่ได้รับเสียง (No Speech)");
                if (micStatusContainer) micStatusContainer.innerText = "ไม่ได้รับเสียง (No Speech Detected)";
            } else {
                showError("ข้อผิดพลาด: " + event.error);
            }
        };

        btnMicToggle.addEventListener('click', function () {
            if (isRecording) {
                recognition.stop();
            } else {
                // Reset status
                if (micStatusContainer) micStatusContainer.innerText = 'กำลังเริ่ม... (Starting...)';
                try {
                    recognition.start();
                } catch (e) {
                    console.error(e);
                    showError("ไม่สามารถเริ่มไมค์ได้: " + e.message);
                }
            }
        });

    } else {
        btnMicToggle.style.display = 'none';
        showError("เบราว์เซอร์นี้ไม่รองรับ Web Speech API กรุณาใช้ Chrome หรือ Edge");
    }
    // --- MediaPipe Hand Gesture Implementation ---
    const videoElement = document.querySelector('.input_video');
    const canvasElement = document.querySelector('.output_canvas');
    let canvasCtx = null;

    // Diagnostic Check
    if (!window.isSecureContext) {
        showError("Camera Error: App is NOT running in a Secure Context (HTTPS). Camera access is blocked by the browser. Please use 'http://localhost:7861' or setup HTTPS.");
        const overlay = document.querySelector('.camera-overlay-text');
        if (overlay) overlay.innerHTML = '<span style="color:red; font-weight:bold;">Error: Not Secure Context (HTTPS required)</span>';
    } else if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        showError("Camera Error: Browser API 'navigator.mediaDevices' is missing. Check permissions or HTTPS.");
        const overlay = document.querySelector('.camera-overlay-text');
        if (overlay) overlay.innerHTML = '<span style="color:red; font-weight:bold;">Error: API Missing (Check HTTPS)</span>';
    }

    if (canvasElement) {
        canvasCtx = canvasElement.getContext('2d');
    }

    let lastActionTime = 0;
    const ACTION_COOLDOWN = 800; // ms (Reduced for better responsiveness)

    function onResults(results) {
        if (!canvasCtx) return;

        // Draw the camera feed - Mirror image for natural interaction
        canvasCtx.save();
        canvasCtx.translate(canvasElement.width, 0);
        canvasCtx.scale(-1, 1);
        canvasCtx.clearRect(0, 0, canvasElement.width, canvasElement.height);
        canvasCtx.drawImage(results.image, 0, 0, canvasElement.width, canvasElement.height);

        if (results.multiHandLandmarks) {
            for (const landmarks of results.multiHandLandmarks) {
                // Draw landmarks
                drawConnectors(canvasCtx, landmarks, HAND_CONNECTIONS, { color: '#00FF00', lineWidth: 2 });
                drawLandmarks(canvasCtx, landmarks, { color: '#FF0000', lineWidth: 1 });

                // Detect Gesture
                detectGesture(landmarks);
            }
        }
        canvasCtx.restore();
    }

    function detectGesture(landmarks) {
        const thumbTip = landmarks[4];
        const indexTip = landmarks[8];

        // Calculate distance (Euclidean) - simplified for 2D (x,y)
        // MediaPipe coords are normalized 0-1
        const distance = Math.sqrt(
            Math.pow(thumbTip.x - indexTip.x, 2) +
            Math.pow(thumbTip.y - indexTip.y, 2)
        );

        // Midpoint for cursor (Visual feedback)
        // NOTE: We used mirroring in drawImage (scale(-1, 1)). 
        // For interaction logic to match the visual mirror, we need to flip the X coordinate.
        // Normalized 0(left) -> 1(right). In mirror mode, visual left is actual right.
        const cursorX_norm = 1 - ((thumbTip.x + indexTip.x) / 2);
        const cursorY_norm = (thumbTip.y + indexTip.y) / 2;

        // Get Canvas Rect for coordinate conversion
        const rect = canvasElement.getBoundingClientRect();
        const clientX = rect.left + (cursorX_norm * rect.width);
        const clientY = rect.top + (cursorY_norm * rect.height);

        // Draw visual cursor on canvas (we are inside canvasCtx.save() with mirroring)
        // Since we are inside the mirrored context, drawing at (1-cursorX_norm) would put it back to original?
        // Let's just draw a circle at the HAND landmarks (which are already mirrored by the context transform)
        // We want to visually show where the "pinch" is happening on the landmarks.
        // The mid point of landmarks[4] and landmarks[8]
        const midX = (thumbTip.x + indexTip.x) / 2;
        const midY = (thumbTip.y + indexTip.y) / 2;

        const PINCH_THRESHOLD = 0.06; // Reduced from 0.08 to avoid accidental triggers

        canvasCtx.beginPath();
        canvasCtx.arc(midX * canvasElement.width, midY * canvasElement.height, 5, 0, 2 * Math.PI); // Reduced radius from 10 to 5
        canvasCtx.fillStyle = distance < PINCH_THRESHOLD ? "rgba(0, 255, 0, 0.5)" : "rgba(255, 255, 255, 0.5)";
        canvasCtx.fill();


        // Pinch Threshold
        if (distance < PINCH_THRESHOLD) {
            // Check Collision using document.elementFromPoint
            // This requires screen coordinates (clientX, clientY) which we calculated above
            const element = document.elementFromPoint(clientX, clientY);

            if (element && element.classList.contains('gesture-box')) {
                // Visual Feedback on the box
                element.classList.add('active');
                setTimeout(() => element.classList.remove('active'), 200);

                // Trigger Action with Cooldown
                const now = Date.now();
                if (now - lastActionTime > ACTION_COOLDOWN) {
                    const action = element.getAttribute('data-action');
                    triggerAction(action);
                    lastActionTime = now;
                }
            }
        }
    }

    function triggerAction(action) {
        // console.log("Triggering Action:", action);

        switch (action) {
            case 'CLEAR':
                if (txtTranscription) txtTranscription.value = "";
                if (micStatusContainer) micStatusContainer.innerText = "Transcription Cleared";
                break;
            case 'SCROLL_UP':
                document.querySelector('.document-pane').scrollBy({ top: -200, behavior: 'smooth' });
                break;
            case 'SCROLL_DOWN':
                document.querySelector('.document-pane').scrollBy({ top: 200, behavior: 'smooth' });
                break;
            case 'PREV':
                // Logic to find current focused input and move previous
                moveFocus(-1);
                break; // Fixed missing break
            case 'NEXT':
                moveFocus(1);
                break;
            case 'SELECT':
                // Select specific element (Checkbox / Radio)
                const active = document.activeElement;
                if (active && (active.type === 'checkbox' || active.type === 'radio')) {
                    active.click();
                    // Visual feedback for click on the PARENT label
                    const visualEl = active.parentElement;
                    if (visualEl) {
                        visualEl.classList.add('gesture-focus');
                        setTimeout(() => visualEl.classList.remove('gesture-focus'), 200);
                        setTimeout(() => visualEl.classList.add('gesture-focus'), 400); // Blink back
                    }
                } else if (txtTranscription) {
                    // Default fallback
                    txtTranscription.select();
                }
                break;
            case 'MOVE':
                // Placeholder for Move/Pinch logic - maybe toggle a mode?
                // For now just log
                break;
            case 'MIC_TOGGLE':
                const micBtn = document.getElementById('btn-mic-toggle');
                if (micBtn) micBtn.click(); // Reuse existing click handler
                break;
            case 'SAVE':
                // Check if Download button exists (PDF ready)
                const downloadBtn = document.getElementById('btn-download-pdf');
                const saveBtn = document.getElementById('btn-save-submit');

                if (downloadBtn) {
                    console.log("Action: SAVE -> Downloading PDF");
                    window.location.href = downloadBtn.href;
                } else if (saveBtn) {
                    console.log("Action: SAVE -> Submitting Form");
                    // Try finding the form and submitting it directly for reliability
                    const form = saveBtn.closest('form');
                    if (form) {
                        form.submit();
                    } else {
                        saveBtn.click(); // Fallback
                    }
                }
                break;
        }
    }



    function moveFocus(direction) {
        // Expanded selector to include checkboxes and radios
        const inputs = Array.from(document.querySelectorAll('input[type="text"], textarea, input[type="checkbox"], input[type="radio"]'));
        const current = document.activeElement;
        const currentIndex = inputs.indexOf(current);

        // Remove focus class from current visual element
        if (current) {
            const currentVisual = (current.type === 'checkbox' || current.type === 'radio') ? current.parentElement : current;
            if (currentVisual) currentVisual.classList.remove('gesture-focus');
        }

        let nextIndex = 0;
        if (currentIndex !== -1) {
            nextIndex = currentIndex + direction;
        }

        // Wrap around logic (optional, but good for UX)
        if (nextIndex < 0) nextIndex = inputs.length - 1;
        if (nextIndex >= inputs.length) nextIndex = 0;

        if (nextIndex >= 0 && nextIndex < inputs.length) {
            const target = inputs[nextIndex];
            target.focus();



            // Add focus class to new visual element
            const targetVisual = (target.type === 'checkbox' || target.type === 'radio') ? target.parentElement : target;
            if (targetVisual) {
                targetVisual.classList.add('gesture-focus');
                // Scroll into view if needed
                targetVisual.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }
    }

    // Initialize MediaPipe Hands
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

        // Initialize Camera
        if (videoElement) {
            const camera = new Camera(videoElement, {
                onFrame: async () => {
                    await hands.send({ image: videoElement });
                },
                width: 480,
                height: 360
            });
            camera.start()
                .then(() => {
                    console.log("Camera started successfully");
                    // Hide the camera overlay text if it's running? Or keep it?
                    // Maybe update it to say "Camera Active"
                })
                .catch(err => {
                    console.error("Camera start error:", err);
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
