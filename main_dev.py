import math
import random

import pygame

from physics_dev import Body, GRAVITY, PhysicsEngine, set_ground_y


WIDTH = 1280
HEIGHT = 720
FPS = 60
FIRE_INTERVAL = 3.0
CANNON_MUZZLE_SPEED = 1480
GROUND_Y = HEIGHT - 40
CANNON_MIN_ANGLE_DEG = 25
CANNON_MAX_ANGLE_DEG = 65
BLOCK_DIRECT_IMPACT_BOOST = 0.95
BLOCK_SPLASH_RADIUS = 100
BLOCK_SPLASH_FORCE = 1.35
BLOCK_SPLASH_NUDGE = 0.98

SKY = (112, 196, 245)
GROUND = (62, 132, 62)
CASTLE_STONE = (178, 180, 184)
CANNON_COLOR = (40, 40, 40)
PROJECTILE_COLOR = (40, 20, 15)
LEFT_COLOR = (65, 206, 110)
RIGHT_COLOR = (230, 135, 65)
TEXT_COLOR = (25, 25, 25)


class CastleBlock:
    MAX_HITS = 3

    def __init__(self, rect: pygame.Rect, side: str):
        self.body = Body(rect=rect, vel=pygame.Vector2(), mass=3.0, dynamic=False)
        self.side = side
        self.hit_count = 0
        self.sprites = self._build_damage_sprites(rect.size)

    @staticmethod
    def _build_damage_sprites(size: tuple[int, int]) -> list[pygame.Surface]:
        width, height = size
        crack_color = (108, 108, 112)
        edge_color = (98, 98, 100)

        def make_base() -> pygame.Surface:
            sprite = pygame.Surface((width, height), pygame.SRCALPHA)
            sprite.fill(CASTLE_STONE)
            pygame.draw.rect(sprite, edge_color, sprite.get_rect(), 1)
            return sprite

        pristine = make_base()

        slight = make_base()
        pygame.draw.line(slight, crack_color, (6, 6), (width - 7, height - 7), 2)
        pygame.draw.line(slight, crack_color, (width // 2, 4), (width // 2 - 4, height // 2), 1)

        major = make_base()
        pygame.draw.line(major, crack_color, (5, 5), (width - 6, height - 6), 2)
        pygame.draw.line(major, crack_color, (width - 6, 6), (6, height - 6), 2)
        pygame.draw.line(major, crack_color, (width // 2, 3), (width // 2 - 8, height // 2), 2)
        pygame.draw.line(major, crack_color, (width // 2 + 2, height // 2), (width - 8, height - 4), 1)

        return [pristine, slight, major]

    def apply_impact(self, amount: float):
        if not self.body.active or amount <= 0:
            return False

        self.body.dynamic = True
        self.hit_count += 1
        if self.hit_count >= self.MAX_HITS:
            self.body.active = False
            return True
        return False

    @property
    def sprite(self):
        damage_stage = min(self.hit_count, self.MAX_HITS - 1)
        return self.sprites[damage_stage]


class Caterpillar:
    def __init__(self, x: int, y: int, side: str):
        self.body = Body(rect=pygame.Rect(x, y, 34, 24), vel=pygame.Vector2(), mass=1.0, dynamic=False)
        self.side = side
        self.fallen = False

    def update(self, dt: float):
        if self.body.dynamic:
            self.body.vel.y += GRAVITY * dt
            self.body.rect.x += int(self.body.vel.x * dt)
            self.body.rect.y += int(self.body.vel.y * dt)
            if self.body.rect.bottom >= GROUND_Y:
                self.body.rect.bottom = GROUND_Y
                self.body.vel.update(0, 0)
                self.fallen = True

    def draw(self, surface: pygame.Surface):
        color = LEFT_COLOR if self.side == "left" else RIGHT_COLOR
        body = self.body.rect
        pygame.draw.ellipse(surface, color, body)
        for i in range(3):
            pygame.draw.circle(surface, color, (body.x + 9 + i * 9, body.bottom - 1), 4)
        pygame.draw.circle(surface, (0, 0, 0), (body.right - 8, body.y + 9), 3)


class Projectile:
    def __init__(self, pos: pygame.Vector2, vel: pygame.Vector2, owner: str):
        self.body = Body(rect=pygame.Rect(0, 0, 10, 10), vel=vel, mass=1.8, dynamic=True)
        self.body.rect.center = (int(pos.x), int(pos.y))
        self.owner = owner
        self.alive = True

    def update(self, dt: float):
        self.body.vel.y += GRAVITY * dt
        self.body.rect.x += int(self.body.vel.x * dt)
        self.body.rect.y += int(self.body.vel.y * dt)
        if (
            self.body.rect.top > HEIGHT
            or self.body.rect.right < 0
            or self.body.rect.left > WIDTH
        ):
            self.alive = False


class Cannon:
    def __init__(self, side: str, base_x: int):
        self.side = side
        self.base = pygame.Vector2(base_x, GROUND_Y - 80)
        self.cooldown = random.uniform(0.0, FIRE_INTERVAL)
        self.barrel_angle = -math.radians((CANNON_MIN_ANGLE_DEG + CANNON_MAX_ANGLE_DEG) / 2)

    def update_and_maybe_fire(self, dt: float, target: pygame.Vector2):
        self.cooldown -= dt
        if self.cooldown > 0:
            return None
        self.cooldown = FIRE_INTERVAL

        del target
        launch_deg = random.uniform(CANNON_MIN_ANGLE_DEG, CANNON_MAX_ANGLE_DEG)
        if self.side == "left":
            angle = -math.radians(launch_deg)
            speed = CANNON_MUZZLE_SPEED
        else:
            angle = math.pi + math.radians(launch_deg)
            speed = CANNON_MUZZLE_SPEED
        self.barrel_angle = angle

        vel = pygame.Vector2(math.cos(angle), math.sin(angle)) * speed
        if self.side == "right":
            vel.x = -abs(vel.x)
        else:
            vel.x = abs(vel.x)
        return Projectile(self.base.copy(), vel, self.side)

    def draw(self, surface: pygame.Surface):
        base_rect = pygame.Rect(self.base.x - 18, self.base.y - 12, 36, 24)
        pygame.draw.rect(surface, CANNON_COLOR, base_rect)
        barrel_length = 34
        tip = (
            int(self.base.x + math.cos(self.barrel_angle) * barrel_length),
            int(self.base.y + math.sin(self.barrel_angle) * barrel_length),
        )
        pygame.draw.line(surface, CANNON_COLOR, self.base, tip, 8)


class Game:
    def __init__(self):
        pygame.init()
        global WIDTH, HEIGHT, GROUND_Y

        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        WIDTH, HEIGHT = self.screen.get_size()
        GROUND_Y = HEIGHT - 40
        set_ground_y(GROUND_Y)
        pygame.display.set_caption("Caterpillar Fall")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("menlo", 24)

        self.castle_rows = 12
        self.castle_cols = 11

        self.left_blocks = self._build_castle("left", 120)
        self.right_blocks = self._build_castle(
            "right", WIDTH - 120 - self.castle_cols * 34
        )
        self.blocks = self.left_blocks + self.right_blocks

        left_top = min(b.body.rect.top for b in self.left_blocks)
        right_top = min(b.body.rect.top for b in self.right_blocks)
        self.left_caterpillar = Caterpillar(170, left_top - 24, "left")
        self.right_caterpillar = Caterpillar(WIDTH - 220, right_top - 24, "right")
        self.caterpillars = [self.left_caterpillar, self.right_caterpillar]

        self.left_cannon = Cannon("left", 90)
        self.right_cannon = Cannon("right", WIDTH - 90)

        self.projectiles: list[Projectile] = []
        self.physics = PhysicsEngine(self.blocks, self.caterpillars)
        self.winner = None

    def _build_castle(self, side: str, start_x: int):
        block_w = 34
        block_h = 24
        block_rect_h = block_h - 2
        rows = self.castle_rows
        cols = self.castle_cols
        blocks = []
        for row in range(rows):
            for col in range(cols):
                if row in (1, 4, 7) and col in (0, cols - 1):
                    continue
                x = start_x + col * block_w
                y = GROUND_Y - block_rect_h - (rows - 1 - row) * block_h
                blocks.append(CastleBlock(pygame.Rect(x, y, block_w - 2, block_rect_h), side))
        return blocks

    def _projectile_hits(self, proj: Projectile):
        target_side = "right" if proj.owner == "left" else "left"
        hit_point = pygame.Vector2(proj.body.rect.center)

        # Hit enemy blocks only; own shots pass through own castle by design.
        for block in self.blocks:
            if not block.body.active:
                continue
            if block.side != target_side:
                continue
            if proj.body.rect.colliderect(block.body.rect):
                impact_momentum = proj.body.vel.length() * proj.body.mass
                block.apply_impact(impact_momentum * 1.05)
                block.body.vel += proj.body.vel * (
                    BLOCK_DIRECT_IMPACT_BOOST * proj.body.mass / max(1.0, block.body.mass)
                )

                for nearby in self.blocks:
                    if not nearby.body.active:
                        continue
                    if nearby.side != target_side or nearby is block:
                        continue
                    distance = hit_point.distance_to(nearby.body.center_vec())
                    if distance < BLOCK_SPLASH_RADIUS:
                        splash = max(0.0, (BLOCK_SPLASH_RADIUS - distance) * BLOCK_SPLASH_FORCE)
                        nearby.apply_impact(splash)
                        nudge = nearby.body.center_vec() - hit_point
                        if nudge.length_squared() > 0:
                            nearby.body.vel += nudge.normalize() * (splash * BLOCK_SPLASH_NUDGE)
                proj.alive = False
                return

        enemy = self.right_caterpillar if target_side == "right" else self.left_caterpillar
        if proj.body.rect.colliderect(enemy.body.rect):
            enemy.body.dynamic = True
            enemy.body.vel += proj.body.vel * 0.65
            proj.alive = False

        if proj.body.rect.bottom >= GROUND_Y:
            proj.alive = False

    def update(self, dt: float):
        if self.winner:
            return

        left_target = pygame.Vector2(self.right_caterpillar.body.rect.center)
        right_target = pygame.Vector2(self.left_caterpillar.body.rect.center)
        left_shot = self.left_cannon.update_and_maybe_fire(dt, left_target)
        right_shot = self.right_cannon.update_and_maybe_fire(dt, right_target)
        if left_shot:
            self.projectiles.append(left_shot)
        if right_shot:
            self.projectiles.append(right_shot)

        for proj in self.projectiles:
            proj.update(dt)
            self._projectile_hits(proj)
        self.projectiles = [p for p in self.projectiles if p.alive]
        self._despawn_destroyed_blocks()

        self.physics.update(dt)

        if self.left_caterpillar.fallen:
            self.winner = "Right"
        elif self.right_caterpillar.fallen:
            self.winner = "Left"

    def _despawn_destroyed_blocks(self):
        self.blocks[:] = [block for block in self.blocks if block.body.active]
        self.left_blocks[:] = [block for block in self.left_blocks if block.body.active]
        self.right_blocks[:] = [block for block in self.right_blocks if block.body.active]

    def draw(self):
        self.screen.fill(SKY)
        pygame.draw.rect(self.screen, GROUND, (0, GROUND_Y, WIDTH, HEIGHT - GROUND_Y))

        for block in self.blocks:
            self.screen.blit(block.sprite, block.body.rect.topleft)

        self.left_cannon.draw(self.screen)
        self.right_cannon.draw(self.screen)

        for proj in self.projectiles:
            pygame.draw.circle(self.screen, PROJECTILE_COLOR, proj.body.rect.center, 5)

        self.left_caterpillar.draw(self.screen)
        self.right_caterpillar.draw(self.screen)

        caption = "Caterpillar Fall · Cannons auto-fire every 3 seconds"
        self.screen.blit(self.font.render(caption, True, TEXT_COLOR), (24, 16))
        if self.winner:
            msg = f"{self.winner} side wins!"
            text = self.font.render(msg, True, (180, 30, 30))
            self.screen.blit(text, (WIDTH // 2 - text.get_width() // 2, 46))

        pygame.display.flip()

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False

            self.update(dt)
            self.draw()

        pygame.quit()


if __name__ == "__main__":
    Game().run()
