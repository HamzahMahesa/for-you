import cv2
import mediapipe as mp
import pygame
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *
import numpy as np
import math
import threading
import time

# ==========================================
# KONFIGURASI & INISIALISASI
# ==========================================
WIDTH, HEIGHT = 1000, 700
NUM_PARTICLES = 1500  

lock = threading.Lock()
shared_data = {
    "mode": 1,
    "target_x": 0.0,
    "target_y": 0.0,
    "target_z": -12.0,
    "frame": None,
    "running": True
}

# ==========================================
# GENERASI DATA BENTUK (PARTIKEL 3D)
# ==========================================
# Mode 1: Kosmos Terbuka (Biru)
pos_space = np.random.uniform(-4.0, 4.0, (NUM_PARTICLES, 3))

# Mode 2: Saturnus (Bola Inti Orange + Cincin Kuning/Orange) - KEMBALI KE KODE AWAL
pos_planet = np.zeros((NUM_PARTICLES, 3))
NUM_SPHERE = 700  
for i in range(NUM_SPHERE):
    phi = np.random.uniform(0, 2 * np.pi)
    costheta = np.random.uniform(-1, 1)
    theta = np.arccos(costheta)
    r = 1.3  
    pos_planet[i, 0] = r * np.sin(theta) * np.cos(phi)
    pos_planet[i, 1] = r * np.sin(theta) * np.sin(phi)
    pos_planet[i, 2] = r * np.cos(theta)

for i in range(NUM_SPHERE, NUM_PARTICLES):
    theta = np.random.uniform(0, 2 * np.pi)
    r = np.random.uniform(1.8, 3.8)  
    pos_planet[i, 0] = r * np.cos(theta)
    pos_planet[i, 1] = np.random.uniform(-0.05, 0.05)  
    pos_planet[i, 2] = r * np.sin(theta)


# -------------------------------------------------------------
# FUNGSI GENERATOR TEKS (OTOMATIS DI TENGAH LAYAR)
# -------------------------------------------------------------
def generate_text_particles(text, scale=3.5, thickness=12, div_factor=70.0):
    # Buat kanvas dasar
    img = np.zeros((300, 1000), dtype=np.uint8)
    cv2.putText(img, text, (50, 200), cv2.FONT_HERSHEY_SIMPLEX, scale, 255, thickness, cv2.LINE_AA)
    
    y_indices, x_indices = np.where(img > 0)
    
    if len(x_indices) == 0:
        return np.random.uniform(-2.0, 2.0, (NUM_PARTICLES, 3))
        
    # Otomatis menghitung titik tengah murni dari piksel teks agar posisinya pas di center grid OpenGL
    mean_x = np.mean(x_indices)
    mean_y = np.mean(y_indices)
    
    x_text = (x_indices - mean_x) / div_factor
    y_text = -(y_indices - mean_y) / div_factor
    z_text = np.random.uniform(-0.1, 0.1, len(x_text))
    
    points = np.stack((x_text, y_text, z_text), axis=-1)
    chosen_indices = np.random.choice(len(points), NUM_PARTICLES)
    return points[chosen_indices]


# Mode 3: 2 Jari -> Huruf "I" Besar (Kuning) - Otomatis Center Tengah
pos_text_I = generate_text_particles("I", scale=5.0, thickness=18, div_factor=55.0)

# Mode 4: 3 Jari -> Tulisan "YOU" (Hijau) - Otomatis Center Tengah
pos_text_YOU = generate_text_particles("YOU", scale=4.0, thickness=14, div_factor=65.0)

# Mode 5: 4 Jari -> Tulisan "sarah" (Tosca) - Otomatis Center Tengah
pos_text_SARAH = generate_text_particles("sarah", scale=3.8, thickness=12, div_factor=65.0)

# Mode 6: Tangan Mengepal -> Bentuk Hati / Love (Pink)
pos_heart = np.zeros((NUM_PARTICLES, 3))
for i in range(NUM_PARTICLES):
    t = np.random.uniform(-np.pi, np.pi)
    p = np.random.uniform(-np.pi, np.pi)
    
    x = 2.0 * (np.sin(t) ** 3)
    y = 2.0 * np.cos(t) - 0.7 * np.cos(2*t) - 0.3 * np.cos(3*t) - 0.1 * np.cos(4*t)
    z = np.sin(p) * 0.4  
    
    pos_heart[i, 0] = x * 0.85
    pos_heart[i, 1] = (y * 0.85) + 0.3  
    pos_heart[i, 2] = z

current_pos = np.copy(pos_space)
target_pos = np.copy(pos_space)

# ==========================================
# FUNGSI LOGIKA DETEKSI GESTUR (JUMLAH JARI)
# ==========================================
def hitung_mode_gestur(hand_landmarks):
    tips = [8, 12, 16, 20]  
    pips = [6, 10, 14, 18]
    
    jari_berdiri = [hand_landmarks.landmark[t].y < hand_landmarks.landmark[p].y for t, p in zip(tips, pips)]
    
    thumb_tip = hand_landmarks.landmark[4]
    thumb_ip = hand_landmarks.landmark[3]
    wrist = hand_landmarks.landmark[0]
    
    jempol_berdiri = abs(thumb_tip.x - wrist.x) > abs(thumb_ip.x - wrist.x)
    total_jari = sum(jari_berdiri) + (1 if jempol_berdiri else 0)
    
    if sum(jari_berdiri) == 0: 
        return 6  # Tangan mengepal -> Love Pink
    elif total_jari == 1:
        return 2  # 1 Jari -> Saturnus Orange
    elif total_jari == 2:
        return 3  # 2 Jari -> Huruf I Kuning
    elif total_jari == 3:
        return 4  # 3 Jari -> Tulisan YOU Hijau
    elif total_jari == 4:
        return 5  # 4 Jari -> Tulisan sarah Tosca
    elif total_jari >= 5:
        return 1  # Telapak terbuka penuh -> Kosmos Biru menyebar
        
    return 1

# ==========================================
# THREAD BACKGROUND: PROSES SELEKSI KAMERA
# ==========================================
def camera_thread_func():
    print("Menginisialisasi kamera laptop...")
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        cap = cv2.VideoCapture(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 480)   
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)
    
    mp_hands = mp.solutions.hands
    mp_drawing = mp.solutions.drawing_utils
    hands = mp_hands.Hands(max_num_hands=1, min_detection_confidence=0.55, min_tracking_confidence=0.55)

    print("Thread kamera berhasil berjalan!")

    while shared_data["running"]:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.01)
            continue

        frame = cv2.flip(frame, 1)  
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = hands.process(rgb_frame)

        local_mode = 1
        local_x, local_y, local_z = 0.0, 0.0, -12.0

        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                mp_drawing.draw_landmarks(
                    frame, hand_landmarks, mp_hands.HAND_CONNECTIONS,
                    mp_drawing.DrawingSpec(color=(0,0,255), thickness=2, circle_radius=2),
                    mp_drawing.DrawingSpec(color=(0,255,0), thickness=2)
                )
                local_mode = hitung_mode_gestur(hand_landmarks)
                
                wrist = hand_landmarks.landmark[0]
                local_x = (wrist.x - 0.5) * 10.0 
                local_y = -(wrist.y - 0.5) * 7.0 
                
                pinky_mcp = hand_landmarks.landmark[17]
                distance = math.sqrt((wrist.x - pinky_mcp.x)**2 + (wrist.y - pinky_mcp.y)**2)
                local_z = -10.0 - (1.0 / (distance + 0.01)) * 0.2

        with lock:
            shared_data["mode"] = local_mode
            shared_data["target_x"] = local_x
            shared_data["target_y"] = local_y
            shared_data["target_z"] = local_z
            shared_data["frame"] = frame.copy()

    cap.release()

camera_thread = threading.Thread(target=camera_thread_func, daemon=True)
camera_thread.start()

time.sleep(1.5)

# ==========================================
# MAIN THREAD: RENDERING GRAFIS 3D (PYGAME)
# ==========================================
pygame.init()
pygame.display.set_mode((WIDTH, HEIGHT), DOUBLEBUF | OPENGL)
pygame.display.set_caption("Custom Space Gesture Controller")

glMatrixMode(GL_PROJECTION)
glLoadIdentity()
gluPerspective(45, (WIDTH / HEIGHT), 0.1, 50.0)
glMatrixMode(GL_MODELVIEW)
glEnable(GL_DEPTH_TEST)

clock = pygame.time.Clock()
rotation_angle = 0.0
hand_x, hand_y, hand_z = 0.0, 0.0, -12.0

cv2.namedWindow("Hand Sensor Monitor", cv2.WINDOW_AUTOSIZE)

while shared_data["running"]:
    pygame.event.pump()
    for event in pygame.event.get():
        if event.type == pygame.QUIT or (event.type == KEYDOWN and event.key == K_ESCAPE):
            shared_data["running"] = False

    with lock:
        current_mode = shared_data["mode"]
        target_hand_x = shared_data["target_x"]
        target_hand_y = shared_data["target_y"]
        target_hand_z = shared_data["target_z"]
        frame = shared_data["frame"]

    if frame is not None:
        mode_labels = {
            1: "KOSMOS (Buka Tangan) - BIRU", 
            2: "SATURNUS (1 Jari) - ORANGE", 
            3: "BENTUK 'I' (2 Jari) - KUNING", 
            4: "TULISAN 'YOU' (3 Jari) - HIJAU",
            5: "TULISAN 'sarah' (4 Jari) - TOSCA",
            6: "HATI (Mengepal) - PINK"
        }
        cv2.putText(frame, f"MODE: {mode_labels[current_mode]}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
        cv2.imshow("Hand Sensor Monitor", frame)
    
    if cv2.waitKey(1) & 0xFF == ord('q'):
        shared_data["running"] = False

    # --- PROSES RENDER OPENGL ---
    glClearColor(0.0, 0.0, 0.0, 1.0)
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    glLoadIdentity()

    hand_x += (target_hand_x - hand_x) * 0.25
    hand_y += (target_hand_y - hand_y) * 0.25
    hand_z += (target_hand_z - hand_z) * 0.25

    # Logika Perpindahan Bentuk dan Kecepatan Rotasi
    if current_mode == 1:
        target_pos = pos_space
        rotation_angle += 0.5 
    elif current_mode == 2:
        target_pos = pos_planet
        rotation_angle += 2.0 
    elif current_mode == 3:
        target_pos = pos_text_I
        rotation_angle = 0.0  
    elif current_mode == 4:
        target_pos = pos_text_YOU
        rotation_angle = 0.0  
    elif current_mode == 5:
        target_pos = pos_text_SARAH
        rotation_angle = 0.0  
    elif current_mode == 6:
        target_pos = pos_heart
        rotation_angle += 1.5  

    current_pos += (target_pos - current_pos) * 0.15

    # Kontrol Translasi Kamera berdasarkan Gerakan Tangan
    if current_mode in [2, 3, 4, 5, 6]:
        glTranslatef(hand_x, hand_y, hand_z)
        if current_mode == 2:
            glRotatef(25, 1.0, 0.0, 0.5) # Kemiringan sudut cincin Saturnus bawaan asli
    else:
        glTranslatef(0.0, 0.0, -12.0)
    
    glRotatef(rotation_angle, 0.0, 1.0, 0.0)

    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glPointSize(4.5)  
    
    glBegin(GL_POINTS)
    for i in range(NUM_PARTICLES):
        if current_mode == 1:
            glColor4f(0.1, 0.5, 1.0, 0.8)   # Biru Kosmos
        elif current_mode == 2:
            if i < NUM_SPHERE:
                glColor4f(1.0, 0.4, 0.0, 0.9)   # Inti Saturnus (Orange)
            else:
                glColor4f(1.0, 0.6, 0.1, 0.6)   # Cincin Saturnus
        elif current_mode == 3:
            glColor4f(1.0, 1.0, 0.0, 0.95)  # Huruf I (Kuning)
        elif current_mode == 4:
            glColor4f(0.0, 1.0, 0.0, 0.95)  # Tulisan YOU (Hijau)
        elif current_mode == 5:
            glColor4f(0.0, 1.0, 0.8, 0.95)  # Tulisan sarah (Tosca)
        elif current_mode == 6:
            glColor4f(1.0, 0.2, 0.5, 0.95)  # Hati/Love (Pink)
            
        glVertex3f(current_pos[i, 0], current_pos[i, 1], current_pos[i, 2])
    glEnd()

    pygame.display.flip()
    clock.tick(60)

cv2.destroyAllWindows()
pygame.quit()