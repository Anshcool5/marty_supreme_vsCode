import pygame
import cv2
import mediapipe as mp
import os
import random

'''
Thank you "Tech With Tim" and "Murtaza's Workshop" for great free python tutorials on youtube that help me so much with this work
Tech With Tim | Making Tetris Tutorial: https://www.youtube.com/watch?v=uoR4ilCWwKA
Murtaza's Workshop | Hand Tracking Tutorial: https://www.youtube.com/watch?v=p5Z_GGRCI5s
'''

#Getting mediapipe: Hands ready
mpHands = mp.solutions.hands
hands = mpHands.Hands()
mpDraw = mp.solutions.drawing_utils

#Capture webcam
cam = cv2.VideoCapture(0)

#Prepare pygame window position, fonts and background music
os.environ['SDL_VIDEO_WINDOW_POS'] ="560,30"
pygame.font.init()
pygame.mixer.init()
pygame.mixer.music.load(os.path.join(os.path.dirname(__file__), 'Tetris_theme.mp3'))

#Global variables
s_width = 800
s_height = 690
play_width = 300  # meaning 300 // 10 = 30 width per block
play_height = 600  # meaning 600 // 20 = 30 height per block
block_size = 30
top_left_x = (s_width - play_width) // 2
top_left_y = s_height - play_height - 10

#1920s-inspired art-deco palette
BG_TOP = (24, 16, 10)
BG_BOTTOM = (10, 7, 5)
PANEL = (36, 24, 16)
PANEL_ACCENT = (196, 154, 86)
GRID_LINE = (92, 68, 40)
TEXT_MAIN = (243, 219, 177)
TEXT_SOFT = (180, 145, 100)
WIN_LINES = 12

#The shapes with all possible rotations
S = [['.....',
      '.....',
      '..00.',
      '.00..',
      '.....'],
     ['.....',
      '..0..',
      '..00.',
      '...0.',
      '.....']]

Z = [['.....',
      '.....',
      '.00..',
      '..00.',
      '.....'],
     ['.....',
      '..0..',
      '.00..',
      '.0...',
      '.....']]

I = [['..0..',
      '..0..',
      '..0..',
      '..0..',
      '.....'],
     ['.....',
      '0000.',
      '.....',
      '.....',
      '.....']]

O = [['.....',
      '.....',
      '.00..',
      '.00..',
      '.....']]

J = [['.....',
      '.0...',
      '.000.',
      '.....',
      '.....'],
     ['.....',
      '..00.',
      '..0..',
      '..0..',
      '.....'],
     ['.....',
      '.....',
      '.000.',
      '...0.',
      '.....'],
     ['.....',
      '..0..',
      '..0..',
      '.00..',
      '.....']]

L = [['.....',
      '...0.',
      '.000.',
      '.....',
      '.....'],
     ['.....',
      '..0..',
      '..0..',
      '..00.',
      '.....'],
     ['.....',
      '.....',
      '.000.',
      '.0...',
      '.....'],
     ['.....',
      '.00..',
      '..0..',
      '..0..',
      '.....']]

T = [['.....',
      '..0..',
      '.000.',
      '.....',
      '.....'],
     ['.....',
      '..0..',
      '..00.',
      '..0..',
      '.....'],
     ['.....',
      '.....',
      '.000.',
      '..0..',
      '.....'],
     ['.....',
      '..0..',
      '.00..',
      '..0..',
      '.....']]

#index 0-6 get you a shape and its corresponding colours
shapes = [S, Z, I, O, J, L, T]
shape_colors = [
    (191, 126, 67),   # warm amber
    (160, 80, 60),    # rust red
    (81, 120, 132),   # muted teal
    (201, 172, 101),  # brass
    (73, 84, 119),    # navy
    (157, 106, 54),   # copper
    (132, 97, 136),   # violet smoke
]

#Class for the Shapes
class Piece(object):  # *
    def __init__(self, x, y, shape):
        self.x = x
        self.y = y
        self.shape = shape
        self.color = shape_colors[shapes.index(shape)]
        self.rotation = 0

#create the grid
def create_grid(locked_pos={}):  # *
    grid = [[(0,0,0) for _ in range(10)] for _ in range(20)]

    for i in range(len(grid)):
        for j in range(len(grid[i])):
            if (j, i) in locked_pos:
                c = locked_pos[(j,i)]
                grid[i][j] = c
    return grid

#convert the shapes into its positions
def convert_shape_format(shape):
    positions = []
    format = shape.shape[shape.rotation % len(shape.shape)]

    for i, line in enumerate(format):
        row = list(line)
        for j, column in enumerate(row):
            if column == '0':
                positions.append((shape.x + j, shape.y + i))

    for i, pos in enumerate(positions):
        positions[i] = (pos[0] - 2, pos[1] - 4)

    return positions

#test whether or not the falling shape is in a valid space
def valid_space(shape, grid):
    accepted_pos = [[(j, i) for j in range(10) if grid[i][j] == (0,0,0)] for i in range(20)]
    accepted_pos = [j for sub in accepted_pos for j in sub]

    formatted = convert_shape_format(shape)

    for pos in formatted:
        if pos not in accepted_pos:
            if pos[1] > -1:
                return False
    return True

#check whether or not the user have lost
def check_lost(positions):
    for pos in positions:
        x, y = pos
        if y < 1:
            return True

    return False

#get a random shape
def get_shape():
    return Piece(5, 0, random.choice(shapes))

#put a text in the middle of the screen
def draw_text_middle(surface, text, size, color, y_offset=0):
    font = pygame.font.SysFont("georgia", size, bold=True)
    label = font.render(text, 1, color)

    center_y = top_left_y + play_height/2 - label.get_height()/2
    surface.blit(label, (top_left_x + play_width /2 - (label.get_width()/2), center_y + y_offset))


def draw_button(surface, rect, text, hovered=False):
    fill = (68, 45, 26) if hovered else PANEL
    pygame.draw.rect(surface, fill, rect, border_radius=8)
    pygame.draw.rect(surface, PANEL_ACCENT, rect, 2, border_radius=8)
    font = pygame.font.SysFont("georgia", 28, bold=True)
    label = font.render(text, 1, TEXT_MAIN)
    surface.blit(label, (rect.centerx - label.get_width() // 2, rect.centery - label.get_height() // 2))


def show_end_screen(surface, title, subtitle):
    play_again = pygame.Rect(s_width // 2 - 210, s_height // 2 + 40, 180, 56)
    quit_btn = pygame.Rect(s_width // 2 + 30, s_height // 2 + 40, 180, 56)

    while True:
        mouse_pos = pygame.mouse.get_pos()
        draw_deco_background(surface)
        draw_text_middle(surface, title, 66, TEXT_MAIN, y_offset=-120)
        draw_text_middle(surface, subtitle, 30, TEXT_SOFT, y_offset=-30)
        draw_button(surface, play_again, "PLAY AGAIN", play_again.collidepoint(mouse_pos))
        draw_button(surface, quit_btn, "QUIT", quit_btn.collidepoint(mouse_pos))
        draw_scanlines(surface)
        pygame.display.update()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return "quit"
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if play_again.collidepoint(event.pos):
                    return "restart"
                if quit_btn.collidepoint(event.pos):
                    return "quit"


def draw_deco_background(surface):
    for y in range(s_height):
        blend = y / float(s_height)
        color = (
            int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * blend),
            int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * blend),
            int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * blend),
        )
        pygame.draw.line(surface, color, (0, y), (s_width, y))

    # light vignette around playfield
    glow = pygame.Surface((play_width + 80, play_height + 80), pygame.SRCALPHA)
    pygame.draw.rect(glow, (223, 180, 104, 34), (0, 0, play_width + 80, play_height + 80), border_radius=18)
    surface.blit(glow, (top_left_x - 40, top_left_y - 40))


def draw_scanlines(surface):
    overlay = pygame.Surface((s_width, s_height), pygame.SRCALPHA)
    for y in range(0, s_height, 4):
        pygame.draw.line(overlay, (0, 0, 0, 24), (0, y), (s_width, y))
    surface.blit(overlay, (0, 0))


def draw_deco_frame(surface):
    frame_rect = (top_left_x - 14, top_left_y - 14, play_width + 28, play_height + 28)
    pygame.draw.rect(surface, PANEL_ACCENT, frame_rect, 4, border_radius=4)
    pygame.draw.rect(surface, GRID_LINE, (top_left_x, top_left_y, play_width, play_height), 2)

    # art-deco corner ticks
    corner = 20
    pygame.draw.line(surface, PANEL_ACCENT, (top_left_x - 14, top_left_y - 14), (top_left_x + corner, top_left_y - 14), 2)
    pygame.draw.line(surface, PANEL_ACCENT, (top_left_x - 14, top_left_y - 14), (top_left_x - 14, top_left_y + corner), 2)
    pygame.draw.line(surface, PANEL_ACCENT, (top_left_x + play_width + 14, top_left_y - 14), (top_left_x + play_width - corner, top_left_y - 14), 2)
    pygame.draw.line(surface, PANEL_ACCENT, (top_left_x + play_width + 14, top_left_y - 14), (top_left_x + play_width + 14, top_left_y + corner), 2)
    pygame.draw.line(surface, PANEL_ACCENT, (top_left_x - 14, top_left_y + play_height + 14), (top_left_x + corner, top_left_y + play_height + 14), 2)
    pygame.draw.line(surface, PANEL_ACCENT, (top_left_x - 14, top_left_y + play_height + 14), (top_left_x - 14, top_left_y + play_height - corner), 2)
    pygame.draw.line(surface, PANEL_ACCENT, (top_left_x + play_width + 14, top_left_y + play_height + 14), (top_left_x + play_width - corner, top_left_y + play_height + 14), 2)
    pygame.draw.line(surface, PANEL_ACCENT, (top_left_x + play_width + 14, top_left_y + play_height + 14), (top_left_x + play_width + 14, top_left_y + play_height - corner), 2)

#draw the lines onto the grid
def draw_grid(surface, grid):
    sx = top_left_x
    sy = top_left_y

    for i in range(len(grid)):
        pygame.draw.line(surface, GRID_LINE, (sx, sy + i*block_size), (sx+play_width, sy+ i*block_size))
        for j in range(len(grid[i])):
            pygame.draw.line(surface, GRID_LINE, (sx + j*block_size, sy),(sx + j*block_size, sy + play_height))

#clear a row
def clear_rows(grid, locked):

    inc = 0
    for i in range(len(grid)-1, -1, -1):
        row = grid[i]
        if (0,0,0) not in row:
            inc += 1
            ind = i
            for j in range(len(row)):
                try:
                    del locked[(j,i)]
                except:
                    continue

    if inc > 0:
        for key in sorted(list(locked), key=lambda x: x[1])[::-1]:
            x, y = key
            if y < ind:
                newKey = (x, y + inc)
                locked[newKey] = locked.pop(key)

    return inc

#draw the window that shows the next shape
def draw_next_shape(shape, surface):
    font = pygame.font.SysFont('georgia', 28, bold=True)
    label = font.render('NEXT', 1, TEXT_MAIN)

    sx = top_left_x + play_width + 50
    sy = top_left_y + play_height/2 - 100
    format = shape.shape[shape.rotation % len(shape.shape)]

    pygame.draw.rect(surface, PANEL, (sx - 16, sy - 50, 170, 220), border_radius=8)
    pygame.draw.rect(surface, PANEL_ACCENT, (sx - 16, sy - 50, 170, 220), 2, border_radius=8)

    for i, line in enumerate(format):
        row = list(line)
        for j, column in enumerate(row):
            if column == '0':
                x = sx + j*block_size
                y = sy + i*block_size
                pygame.draw.rect(surface, shape.color, (x, y, block_size, block_size), 0, border_radius=4)
                pygame.draw.rect(surface, (248, 228, 190), (x + 4, y + 4, block_size - 8, block_size - 8), 1, border_radius=3)

    surface.blit(label, (sx + 32, sy - 40))

#draw the main window
def draw_window(surface, grid, score=0):
    draw_deco_background(surface)

    pygame.font.init()
    font = pygame.font.SysFont('georgia', 56, bold=True)
    label = font.render('TETRIS 1926', 1, TEXT_MAIN)

    surface.blit(label, (top_left_x + play_width / 2 - (label.get_width() / 2), 15))

    #show current score
    font = pygame.font.SysFont('georgia', 28, bold=True)
    label = font.render('SCORE: ' + str(score), 1, TEXT_SOFT)

    sx = top_left_x + play_width + 50
    sy = top_left_y + play_height/2 - 100

    pygame.draw.rect(surface, PANEL, (sx - 16, sy + 110, 170, 60), border_radius=8)
    pygame.draw.rect(surface, PANEL_ACCENT, (sx - 16, sy + 110, 170, 60), 2, border_radius=8)
    surface.blit(label, (sx + 4, sy + 125))

    for i in range(len(grid)):
        for j in range(len(grid[i])):
            color = grid[i][j]
            x = top_left_x + j*block_size
            y = top_left_y + i*block_size
            pygame.draw.rect(surface, color, (x, y, block_size, block_size), 0, border_radius=4)
            if color != (0, 0, 0):
                pygame.draw.rect(surface, (248, 228, 190), (x + 4, y + 4, block_size - 8, block_size - 8), 1, border_radius=3)

    draw_deco_frame(surface)
    draw_grid(surface, grid)
    draw_scanlines(surface)

#add scores that correspond to the amount of rows cleared
def add_score(rows):
    conversion = {
        0: 0,
        1: 40,
        2: 100,
        3: 300,
        4: 1200
    }
    return conversion.get(rows)

#THE MAIN FUNCTION THAT RUNS THE GAME
def main(win):
    locked_positions = {}
    grid = create_grid(locked_positions)

    change_piece = False
    current_piece = get_shape()
    next_piece = get_shape()
    clock = pygame.time.Clock()
    fall_time = 0
    fall_speed_real = 0.8
    fall_speed = fall_speed_real
    level_time = 0
    score = 0

    left_wait = 0
    right_wait = 0
    rotate_wait = 0
    down_wait = 0
    fall_speed_down = 0.3
    lines_cleared = 0

    # Cooldowns smooth gesture inputs and reduce jitter / repeated accidental moves.
    move_cooldown = 0
    rotate_cooldown = 0
    drop_cooldown = 0

    #THE MAIN WHILE LOOP
    while True:
        grid = create_grid(locked_positions)

        fall_time += clock.get_rawtime()
        level_time += clock.get_rawtime()
        clock.tick()

        if move_cooldown > 0:
            move_cooldown -= 1
        if rotate_cooldown > 0:
            rotate_cooldown -= 1
        if drop_cooldown > 0:
            drop_cooldown -= 1

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                cv2.destroyAllWindows()
                return "quit"
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                cv2.destroyAllWindows()
                return "quit"

        #Set up the hand tracker
        success, img = cam.read()
        if not success:
            continue
        imgg = cv2.flip(img, 1)
        imgRGB = cv2.cvtColor(imgg, cv2.COLOR_BGR2RGB)
        results = hands.process(imgRGB)

        gesture_detected = False
        if results.multi_hand_landmarks:
            for handLms in results.multi_hand_landmarks:
                for id, lm in enumerate(handLms.landmark):
                    h, w, c = imgg.shape
                    if id == 0:
                        x = []
                        y = []
                    x.append(int((lm.x) * w))
                    y.append(int((1 - lm.y) * h))

                    #This will track the hand gestures
                    if len(y) > 20:
                        left_pose = (x[0] > x[3] > x[4]) and not(y[20] > y[17])
                        right_pose = not(x[0] > x[3] > x[4]) and (y[20] > y[17])
                        rotate_pose = (x[0] > x[3] > x[4]) and (y[20] > y[17])

                        if left_pose:
                            left_wait += 1
                            right_wait = 0
                            rotate_wait = 0
                            down_wait = 0
                            gesture_detected = True
                        elif right_pose:
                            right_wait += 1
                            left_wait = 0
                            rotate_wait = 0
                            down_wait = 0
                            gesture_detected = True
                        elif rotate_pose:
                            rotate_wait += 1
                            left_wait = 0
                            right_wait = 0
                            down_wait = 0
                            gesture_detected = True


                mpDraw.draw_landmarks(imgg, handLms, mpHands.HAND_CONNECTIONS)

        if not gesture_detected:
            down_wait += 1
            left_wait = 0
            right_wait = 0
            rotate_wait = 0

        cv2.namedWindow("WebCam")
        cv2.moveWindow("WebCam", 20, 121)
        cv2.imshow("WebCam", imgg)
        cv2.waitKey(1)

        #every 10 sec, shapes move 0.03 sec faster (peak at 0.25)
        if level_time/1000 > 10:
            level_time = 0
            if fall_speed_real > 0.25:
                fall_speed_real -= 0.03

        #if enough time (fall_speed) have passsed, piece moves down 1 block
        if fall_time/1000 > fall_speed:
            fall_time = 0
            current_piece.y += 1
            if not(valid_space(current_piece, grid)) and current_piece.y > 0:
                current_piece.y -= 1
                change_piece = True

        #"if you gesture to the LEFT for at least 4 frames, piece move LEFT"
        if left_wait >= 3 and move_cooldown == 0:
            current_piece.x -= 1
            if not (valid_space(current_piece, grid)):
                current_piece.x += 1
            move_cooldown = 4
            left_wait = 0
            right_wait = 0
            rotate_wait = 0
            down_wait = 0

        #"if you gesture to the RIGHT for at least 4 frames, piece move RIGHT"
        if right_wait >= 3 and move_cooldown == 0:
            current_piece.x += 1
            if not (valid_space(current_piece, grid)):
                current_piece.x -= 1
            move_cooldown = 4
            left_wait = 0
            right_wait = 0
            rotate_wait = 0
            down_wait = 0

        #"if you gesture to ROTATE  for at least 4 frames, piece ROTATES"
        if rotate_wait >= 3 and rotate_cooldown == 0:
            current_piece.rotation += 1
            if not (valid_space(current_piece, grid)):
                current_piece.rotation -= 1
            rotate_cooldown = 8
            left_wait = 0
            right_wait = 0
            rotate_wait = 0
            down_wait = 0

        #"if you gesture to go DOWN (no hand on the screen) for at least 5 frames, piece go DOWN (moves very fast)"
        if down_wait >= 5 and drop_cooldown == 0:
            fall_speed = fall_speed_down
            drop_cooldown = 10
            left_wait = 0
            right_wait = 0
            rotate_wait = 0
            down_wait = 0

        shape_pos = convert_shape_format(current_piece)

        #colour the grid where the shape is
        for i in range(len(shape_pos)):
            x, y = shape_pos[i]
            if y > -1:
                grid[y][x] = current_piece.color

        if change_piece:
            for pos in shape_pos:
                p = (pos[0], pos[1])
                locked_positions[p] = current_piece.color
            current_piece = next_piece
            next_piece = get_shape()
            change_piece = False
            cleared = clear_rows(grid, locked_positions)
            lines_cleared += cleared
            score += add_score(cleared)
            fall_speed = fall_speed_real
            down_wait = 0

        draw_window(win, grid, score)
        draw_next_shape(next_piece, win)
        pygame.display.update()

        if lines_cleared >= WIN_LINES:
            cv2.destroyAllWindows()
            return show_end_screen(win, "YOU WON!", "Twelve lines cleared. Encore?")

        if check_lost(locked_positions):
            cv2.destroyAllWindows()
            return show_end_screen(win, "YOU LOST!", "Take a bow and run it back.")

#Menu screen that will lead to the main function
def main_menu(win):
    run = True
    start_btn = pygame.Rect(s_width // 2 - 210, s_height // 2 + 40, 180, 56)
    quit_btn = pygame.Rect(s_width // 2 + 30, s_height // 2 + 40, 180, 56)

    while run:
        mouse_pos = pygame.mouse.get_pos()
        draw_deco_background(win)
        draw_text_middle(win, 'TETRIS 1926', 74, TEXT_MAIN, y_offset=-120)
        draw_text_middle(win, 'HAND-GESTURE EDITION', 30, TEXT_SOFT, y_offset=-30)
        draw_button(win, start_btn, "START", start_btn.collidepoint(mouse_pos))
        draw_button(win, quit_btn, "QUIT", quit_btn.collidepoint(mouse_pos))
        draw_scanlines(win)
        pygame.display.update()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                run = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                run = False
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if start_btn.collidepoint(event.pos):
                    pygame.mixer.music.play(-1)
                    result = main(win)
                    while result == "restart":
                        result = main(win)
                    if result == "quit":
                        run = False
                if quit_btn.collidepoint(event.pos):
                    run = False

    cv2.destroyAllWindows()
    pygame.display.quit()

win = pygame.display.set_mode((s_width, s_height))
pygame.display.set_caption('TETRIS 1926')
main_menu(win)
