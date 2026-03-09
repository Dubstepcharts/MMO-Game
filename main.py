import pygame
import socket
import json
import threading
import time
import math
import sys

pygame.init()

window = pygame.display.set_mode((500, 500))
pygame.display.set_caption("Мультиплеерная игра")
clock = pygame.time.Clock()

HOST = '127.0.0.1'
PORT = 5555

game = True
game_menu = 0
player_id = None
local_player = None
player_speed = 5
client_socket = None
thread_recv = None
thread_send = None
connection_active = True
send_thread_started = False


remote_players = {}  


try:
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect((HOST, PORT))
    print(f"[КЛИЕНТ] Подключен к серверу {HOST}:{PORT}")

    data = client_socket.recv(1024).decode()
    player_id = json.loads(data)['id']
    print(f"[КЛИЕНТ] Получен ID: {player_id}")
except Exception as e:
    print(f"[ОШИБКА] Не удалось подключиться: {e}")
    pygame.quit()
    sys.exit()

# Класс для чужого игрока с интерполяцией (плавным движением)
class RemotePlayer:
    def __init__(self, pid, x, y, color):
        self.id = pid
        self.target_x = x  # Целевая позиция от сервера
        self.target_y = y
        self.current_x = x  # Текущая плавная позиция
        self.current_y = y
        self.color = color
        self.width = 50
        self.height = 50
        self.speed = 0.3  # Скорость интерполяции (0-1, чем меньше, тем плавнее)
        
    def update_target(self, x, y):
        """Обновляет целевую позицию от сервера"""
        self.target_x = x
        self.target_y = y
    
    def update_smooth(self):
        """Плавно двигается к целевой позиции"""
        # Разница между текущей и целевой позицией
        dx = self.target_x - self.current_x
        dy = self.target_y - self.current_y
        
        # Плавно приближаемся к цели
        self.current_x += dx * self.speed
        self.current_y += dy * self.speed
        
        # Если очень близко к цели - фиксируем точно
        if abs(dx) < 0.5 and abs(dy) < 0.5:
            self.current_x = self.target_x
            self.current_y = self.target_y
    
    def draw(self, surface):
        pygame.draw.rect(surface, self.color, (self.current_x, self.current_y, self.width, self.height))
        # Рисуем ID для отладки
        font = pygame.font.SysFont('arial', 16)
        text = font.render(str(self.id), True, (0, 0, 0))
        surface.blit(text, (self.current_x + 20, self.current_y + 15))

# Класс локального игрока
class Player:
    def __init__(self, pid, x, y, color):
        self.id = pid
        self.x = x
        self.y = y
        self.color = color
        self.width = 50
        self.height = 50
        print(f"[СОЗДАН] Игрок {pid} на ({x}, {y})")
    
    def move(self):
        keys = pygame.key.get_pressed()
        moved = False
        
        if keys[pygame.K_w] and self.y > 5:
            self.y -= player_speed
            moved = True
        if keys[pygame.K_s] and self.y < 500 - self.height - 5:
            self.y += player_speed
            moved = True
        if keys[pygame.K_a] and self.x > 5:
            self.x -= player_speed
            moved = True
        if keys[pygame.K_d] and self.x < 500 - self.width - 5:
            self.x += player_speed
            moved = True
        
        return moved
    
    def draw(self, surface):
        pygame.draw.rect(surface, self.color, (self.x, self.y, self.width, self.height))
        # Рисуем ID для отладки
        font = pygame.font.SysFont('arial', 16)
        text = font.render(str(self.id), True, (0, 0, 0))
        surface.blit(text, (self.x + 20, self.y + 15))

# Класс меню
class Menu:
    def __init__(self, x=150, y=150, width=200, height=200, color=(0, 255, 255)):
        self.rect = pygame.Rect(x, y, width, height)
        self.rect_game = pygame.Rect(x + 50, y + 5, width - 100, height - 150)
        self.rect_options = pygame.Rect(x + 35, y + 60, width - 70, height - 150)
        self.rect_quit = pygame.Rect(x + 50, y + 115, width - 100, height - 150)
        self.color = color
        self.text_game = pygame.font.SysFont('comicsans', 30).render('Game', 1, (0, 255, 0))
        self.text_options = pygame.font.SysFont('comicsans', 30).render('Options', 1, (0, 255, 0))
        self.text_quit = pygame.font.SysFont('comicsans', 30).render('Quit', 1, (0, 255, 0))
    
    def draw(self):
        pygame.draw.rect(window, self.color, self.rect)
        pygame.draw.rect(window, (0, 0, 0), self.rect_game)
        pygame.draw.rect(window, (0, 0, 0), self.rect_options)
        pygame.draw.rect(window, (0, 0, 0), self.rect_quit)
        window.blit(self.text_game, (self.rect_game.x + 10, self.rect_game.y + 10))
        window.blit(self.text_options, (self.rect_options.x + 10, self.rect_options.y + 10))
        window.blit(self.text_quit, (self.rect_quit.x + 10, self.rect_quit.y + 10))

# Класс Intell (враг)
class Intell:
    def __init__(self, x, y, width, height, color):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.color = color
        self.center_x = 250
        self.center_y = 250
        self.radius = 100
        self.angle = 0
        self.speed = 0.02
    
    def draw(self):
        pygame.draw.rect(window, self.color, (self.x, self.y, self.width, self.height))
    
    def move_circle(self):
        self.angle += self.speed
        self.x = self.center_x + self.radius * math.cos(self.angle)
        self.y = self.center_y + self.radius * math.sin(self.angle)

# Функция отправки данных
def send_data():
    """Отправляет свои координаты на сервер"""
    global connection_active, game, send_thread_started
    
    print("[ПОТОК-ОТПРАВКА] Запущен")
    last_send = time.time()
    
    while connection_active and game and client_socket:
        try:
            # Отправляем не чаще чем раз в 50мс
            now = time.time()
            if now - last_send >= 0.05:  # 50мс
                if local_player:
                    data = json.dumps({
                        'x': local_player.x, 
                        'y': local_player.y
                    })
                    client_socket.send(data.encode())
                last_send = now
            else:
                time.sleep(0.01)  # Немного отдыхаем
                
        except (socket.error, BrokenPipeError, AttributeError) as e:
            print(f"[ПОТОК-ОТПРАВКА] Ошибка: {e}")
            connection_active = False
            break
    
    print("[ПОТОК-ОТПРАВКА] Завершен")
    send_thread_started = False

# Функция приема данных
def receive_data():
    """Получает данные обо всех игроках от сервера"""
    global connection_active, game, remote_players, local_player
    
    print("[ПОТОК-ПРИЕМ] Запущен")
    
    while connection_active and game and client_socket:
        try:
            client_socket.settimeout(1.0)
            
            try:
                data = client_socket.recv(4096).decode()
            except socket.timeout:
                continue
            
            if data:
                try:
                    new_data = json.loads(data)
                    if 'players' in new_data:
                        received = new_data['players']
                        
                        # Обновляем или создаем RemotePlayer для чужих игроков
                        for pid_str, pdata in received.items():
                            pid = int(pid_str)
                            
                            # Преобразуем цвет
                            color = pdata['color']
                            if isinstance(color, list):
                                color = tuple(color)
                            
                            if pid == player_id:
                                # Это наш игрок - если локальный игрок еще не создан, создаем
                                if local_player is None:
                                    # Будет создан в главном цикле
                                    pass
                            else:
                                # Это чужой игрок
                                if pid in remote_players:
                                    # Обновляем целевую позицию существующего игрока
                                    remote_players[pid].update_target(pdata['x'], pdata['y'])
                                    remote_players[pid].color = color
                                else:
                                    # Создаем нового удаленного игрока
                                    remote_players[pid] = RemotePlayer(pid, pdata['x'], pdata['y'], color)
                                    print(f"[СОЗДАН УДАЛЕННЫЙ] Игрок {pid}")
                        
                        # Удаляем отключившихся игроков
                        current_ids = [int(pid) for pid in received.keys()]
                        for pid in list(remote_players.keys()):
                            if pid not in current_ids:
                                del remote_players[pid]
                                print(f"[УДАЛЕН] Игрок {pid}")
                                
                except json.JSONDecodeError:
                    pass
                    
        except (socket.error, ConnectionResetError, ConnectionAbortedError) as e:
            print(f"[ПОТОК-ПРИЕМ] Ошибка соединения: {e}")
            connection_active = False
            break
    
    print("[ПОТОК-ПРИЕМ] Завершен")

# Запускаем поток приема
if client_socket:
    thread_recv = threading.Thread(target=receive_data, daemon=True)
    thread_recv.start()

# Создаем объекты
menu = Menu()
II = Intell(100, 200, 50, 50, (255, 0, 0))

# Главный цикл
print("[ГЛАВНЫЙ ЦИКЛ] Запуск...")

while game:
    # Обработка событий
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            game = False
    
    # === СОЗДАНИЕ ЛОКАЛЬНОГО ИГРОКА ===
    if local_player is None and player_id is not None:
        # Ждем пока сервер пришлет наши данные
        # Вместо проверки players, просто создаем с начальными координатами
        # Сервер все равно пришлет правильные, но мы их не используем для локального игрока
        color = (255, 0, 0) if player_id == 0 else (0, 0, 255)  # Примерные цвета
        local_player = Player(player_id, 225, 225, color)
        
        # Запускаем поток отправки ТОЛЬКО ОДИН РАЗ
        if client_socket and not send_thread_started:
            send_thread_started = True
            thread_send = threading.Thread(target=send_data, daemon=True)
            thread_send.start()
    
    # Отрисовка
    window.fill((255, 255, 255))
    
    if game_menu == 0:
        menu.draw()
        
        mouse_pos = pygame.mouse.get_pos()
        mouse_click = pygame.mouse.get_pressed()
        
        if mouse_click[0]:
            if menu.rect_game.collidepoint(mouse_pos):
                game_menu = 1
                print("[МЕНЮ] Запуск игры")
            if menu.rect_options.collidepoint(mouse_pos):
                game_menu = 2
            if menu.rect_quit.collidepoint(mouse_pos):
                game = False
    
    elif game_menu == 1:
        # Обновляем плавное движение удаленных игроков
        for remote in remote_players.values():
            remote.update_smooth()
        
        # Рисуем удаленных игроков
        for remote in remote_players.values():
            remote.draw(window)
        
        # Рисуем локального игрока (поверх всех)
        if local_player:
            local_player.draw(window)
            
            # Двигаем локального игрока
            local_player.move()
        
        # Враг
        II.draw()
        
        keys = pygame.key.get_pressed()
        if keys[pygame.K_c]:
            II.move_circle()
    
    elif game_menu == 2:
        font = pygame.font.SysFont('comicsans', 30)
        text = font.render("Options (Press ESC to return)", 1, (0, 0, 0))
        window.blit(text, (100, 200))
        
        keys = pygame.key.get_pressed()
        if keys[pygame.K_ESCAPE]:
            game_menu = 0
    
    pygame.display.update()
    clock.tick(60)

# Завершение
print("[ЗАВЕРШЕНИЕ] Закрытие программы...")
connection_active = False
time.sleep(0.5)

if client_socket:
    try:
        client_socket.close()
    except:
        pass

pygame.quit()
print("[ЗАВЕРШЕНИЕ] Программа закрыта")