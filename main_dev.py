import math
import random

import pygame

from physics_dev import Body, GRAVITY, PhysicsEngine, set_ground_y, set_screen_width


WIDTH = 1280
HEIGHT = 720
FPS = 60
CASTLE_HEAL_INTERVAL = 30.0
CANNON_MUZZLE_SPEED = 1530
CANNON_MIN_SPEED = 900
CANNON_MAX_SPEED = 1800
TURN_TIME_LIMIT = 30.0
TRACER_STEP_TIME = 0.12
TRACER_STEPS = 35
GROUND_Y = HEIGHT - 40
CANNON_MIN_ANGLE_DEG = 25
CANNON_MAX_ANGLE_DEG = 65
BLOCK_DIRECT_IMPACT_BOOST = 2.95
BLOCK_SPLASH_RADIUS = 50
BLOCK_SPLASH_FORCE = 4.35
BLOCK_SPLASH_NUDGE = 2.98

SKY = (112, 196, 245)
GROUND = (62, 132, 62)
CASTLE_STONE = (178, 180, 184)
CANNON_COLOR = (40, 40, 40)
PROJECTILE_COLOR = (40, 20, 15)
LEFT_COLOR = (65, 206, 110)
RIGHT_COLOR = (230, 135, 65)
TEXT_COLOR = (25, 25, 25)
MENU_BACKDROP = (28, 34, 44, 225)
MENU_HIGHLIGHT = (244, 194, 66)

DAMAGE_OPTIONS = (
    ("Normal", 1),
    ("High", 2),
    ("Extreme", 4),
    ("Devastating", 5),
    ("10x", 10),
    ("20x", 20),
    ("50x", 50),
)

# Each collision setting has seven steps and keeps the original value in the
# middle. This makes it easy to experiment without losing the default feel.
RADIUS_OPTIONS = (15, 25, 35, BLOCK_SPLASH_RADIUS, 70, 90, 120)
IMPACT_FORCE_OPTIONS = (0.75, 1.25, 2.0, BLOCK_DIRECT_IMPACT_BOOST, 4.0, 5.5, 7.5)
SPLASH_FORCE_OPTIONS = (1.0, 2.0, 3.0, BLOCK_SPLASH_FORCE, 6.0, 8.0, 11.0)
SPLASH_NUDGE_OPTIONS = (0.5, 1.0, 2.0, BLOCK_SPLASH_NUDGE, 4.0, 5.5, 7.0)
# Rain is intentionally frantic by default: these bounds are one tenth of the
# original 1.25--4.0 second range.  The range keeps each spawn unpredictable.
CANNON_RAIN_MIN_INTERVAL = 0.125
CANNON_RAIN_MAX_INTERVAL = 0.4
CANNON_RAIN_SPEED_OPTIONS = (1, 2, 3, 5, 10, 20, 50)
CANNON_RAIN_MIN_FALL_SPEED = 180
CANNON_RAIN_MAX_FALL_SPEED = 360

# The two edge-mounted gatlings share a burst clock.  Each weapon fires the
# full burst, so an attack sends an equal crossfire from both sides.
GATLING_BURST_SIZE = 150
GATLING_FIRE_RATE_OPTIONS = (5, 10, 15, 20, 25, 30, 35, 40, 45, 50)
GATLING_INTERVAL_OPTIONS = (
    (5, 10),
    (10, 15),
    (15, 20),
    (20, 30),
    (30, 45),
    (45, 60),
    (60, 75),
    (75, 90),
    (90, 105),
    (105, 120),
)
GATLING_AIM_OPTIONS = (-45, -40, -35, -30, -25, -20, -15, -10, -5, 0)
GATLING_POWER_OPTIONS = (1500, 1750, 2000, 2250, 2500, 2750, 3000, 3250, 3500, 3750)
GATLING_SPRAY_DEGREES = 8
OPTION_MENU_COUNT = 12

# Tornado dimensions and force constants are expressed in screen-space units.
# Forces taper continuously at the influence boundary, which avoids the abrupt
# velocity jumps that a simple collision volume would create.
TORNADO_INFLUENCE_RADIUS_RATIO = 0.36
TORNADO_CORE_RADIUS_RATIO = 0.045
TORNADO_HEIGHT_RATIO = 0.72
TORNADO_MAX_WIND_SPEED = 1180.0
TORNADO_UPDRAFT_SPEED = 820.0
TORNADO_RESPONSE = 3.8


class Tornado:
    """A Rankine-like vortex with inflow, rotation, updraft, and gusts.

    This is intentionally a velocity-field model rather than a single radial
    impulse.  Air spirals inward outside the core, rotates as a near-solid body
    inside it, rises more strongly near the funnel, and ejects objects that
    pass through the very center.  Exponential velocity relaxation keeps the
    result stable across varying frame rates.
    """

    def __init__(self):
        self.age = 0.0

    @property
    def center(self) -> pygame.Vector2:
        return pygame.Vector2(WIDTH * 0.5, GROUND_Y)

    @property
    def influence_radius(self) -> float:
        return max(260.0, WIDTH * TORNADO_INFLUENCE_RADIUS_RATIO)

    @property
    def core_radius(self) -> float:
        return max(48.0, WIDTH * TORNADO_CORE_RADIUS_RATIO)

    @property
    def height(self) -> float:
        return HEIGHT * TORNADO_HEIGHT_RATIO

    def update(self, dt: float, blocks: list, projectiles: list) -> None:
        self.age += dt
        for block in blocks:
            if block.body.active:
                self._apply_wind(block.body, dt, aerodynamic_scale=0.72)
        for projectile in projectiles:
            if projectile.alive:
                self._apply_wind(projectile.body, dt, aerodynamic_scale=1.15)

    def _apply_wind(self, body: Body, dt: float, aerodynamic_scale: float) -> None:
        position = body.center_vec()
        offset = position - self.center
        distance = offset.length()
        if distance >= self.influence_radius:
            return

        # Smoothstep falloff represents diminishing winds at the outer edge.
        normalized = distance / self.influence_radius
        influence = (1.0 - normalized) ** 2 * (1.0 + 2.0 * normalized)
        radial = offset.normalize() if distance > 0.01 else pygame.Vector2(1, 0)
        tangent = pygame.Vector2(-radial.y, radial.x)
        core_fraction = min(1.0, distance / self.core_radius)
        rotation = TORNADO_MAX_WIND_SPEED * (
            core_fraction if distance < self.core_radius else 1.0 / core_fraction
        )

        # Low-frequency gusts make trajectories irregular without unstable
        # frame-to-frame random impulses.
        gust = 1.0 + 0.16 * math.sin(
            self.age * 4.7 + position.x * 0.021 + position.y * 0.013
        )
        inflow_speed = 330.0 * influence * (0.35 + 0.65 * core_fraction)
        updraft = TORNADO_UPDRAFT_SPEED * influence * (1.0 - 0.45 * normalized)
        target_velocity = tangent * rotation * gust - radial * inflow_speed
        target_velocity.y -= updraft
        # The side-on 2D projection can point the rotational tangent downward;
        # preserve the vortex's physical vertical updraft in that case.
        target_velocity.y = min(target_velocity.y, -updraft * 0.35)

        # Objects entering the eye are lofted and expelled instead of becoming
        # trapped at an infinite-force singularity.
        if distance < self.core_radius * 0.42:
            target_velocity += radial * (
                520.0 * (1.0 - distance / (self.core_radius * 0.42))
            )

        mass_response = aerodynamic_scale / math.sqrt(max(0.4, body.mass))
        blend = 1.0 - math.exp(-TORNADO_RESPONSE * influence * mass_response * min(dt, 0.05))
        if not body.dynamic and influence * aerodynamic_scale > 0.09:
            body.dynamic = True
        if body.dynamic:
            body.vel += (target_velocity - body.vel) * blend

    def draw(self, surface: pygame.Surface) -> None:
        base_x = int(self.center.x)
        base_y = int(self.center.y)
        top_y = int(base_y - self.height)
        funnel = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)

        # Translucent, overlapping bands convey a broad rotating funnel while
        # leaving projectiles and castle pieces readable in front of it.
        band_count = 18
        for index in range(band_count):
            t = index / (band_count - 1)
            y = int(base_y - t * self.height)
            half_width = int(
                self.core_radius
                * (0.48 + 2.45 * t)
                * (1.0 + 0.08 * math.sin(self.age * 3.2 + index))
            )
            color = (198, 203, 207, 30 + int(42 * (1.0 - t)))
            pygame.draw.ellipse(funnel, color, (base_x - half_width, y - 16, half_width * 2, 32), 5)

        veil_points = [
            (base_x - int(self.core_radius * 0.38), base_y),
            (base_x - int(self.core_radius * 2.7), top_y),
            (base_x + int(self.core_radius * 2.7), top_y),
            (base_x + int(self.core_radius * 0.38), base_y),
        ]
        pygame.draw.polygon(funnel, (174, 181, 187, 42), veil_points)
        surface.blit(funnel, (0, 0))


class CastleBlock:
    MAX_HITS = 12
    HITS_PER_DAMAGE_STAGE = 4

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

    def apply_impact(self, amount: int = 1):
        if not self.body.active or amount <= 0:
            return False

        self.body.dynamic = True
        self.hit_count += amount
        if self.hit_count >= self.MAX_HITS:
            self.body.active = False
            return True
        return False

    def heal(self, amount: int = 1):
        """Repair damage without reviving a block that has been destroyed."""
        if not self.body.active or amount <= 0:
            return
        self.hit_count = max(0, self.hit_count - amount)

    @property
    def sprite(self):
        damage_stage = min(self.hit_count // self.HITS_PER_DAMAGE_STAGE, len(self.sprites) - 1)
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
        self.aim_angle_deg = (CANNON_MIN_ANGLE_DEG + CANNON_MAX_ANGLE_DEG) / 2
        self.muzzle_speed = float(CANNON_MUZZLE_SPEED)

    def _launch_angle_rad(self) -> float:
        launch_deg = self.aim_angle_deg
        if self.side == "left":
            angle = -math.radians(launch_deg)
        else:
            angle = math.pi + math.radians(launch_deg)
        return angle

    def adjust_aim(self, delta_deg: float):
        self.aim_angle_deg = max(CANNON_MIN_ANGLE_DEG, min(CANNON_MAX_ANGLE_DEG, self.aim_angle_deg + delta_deg))

    def adjust_speed(self, delta: float):
        self.muzzle_speed = max(CANNON_MIN_SPEED, min(CANNON_MAX_SPEED, self.muzzle_speed + delta))

    def fire(self):
        angle = self._launch_angle_rad()
        speed = self.muzzle_speed

        vel = pygame.Vector2(math.cos(angle), math.sin(angle)) * speed
        if self.side == "right":
            vel.x = -abs(vel.x)
        else:
            vel.x = abs(vel.x)
        return Projectile(self.base.copy(), vel, self.side)

    def tracer_points(self) -> list[tuple[int, int]]:
        angle = self._launch_angle_rad()
        velocity = pygame.Vector2(math.cos(angle), math.sin(angle)) * self.muzzle_speed
        if self.side == "right":
            velocity.x = -abs(velocity.x)
        else:
            velocity.x = abs(velocity.x)

        points: list[tuple[int, int]] = []
        for i in range(1, TRACER_STEPS + 1):
            t = i * TRACER_STEP_TIME
            x = self.base.x + velocity.x * t
            y = self.base.y + velocity.y * t + 0.5 * GRAVITY * t * t
            if x < 0 or x > WIDTH or y > HEIGHT:
                break
            points.append((int(x), int(y)))
        return points

    def draw(self, surface: pygame.Surface):
        base_rect = pygame.Rect(self.base.x - 18, self.base.y - 12, 36, 24)
        pygame.draw.rect(surface, CANNON_COLOR, base_rect)
        barrel_length = 34
        barrel_angle = self._launch_angle_rad()
        tip = (
            int(self.base.x + math.cos(barrel_angle) * barrel_length),
            int(self.base.y + math.sin(barrel_angle) * barrel_length),
        )
        pygame.draw.line(surface, CANNON_COLOR, self.base, tip, 8)


class Gatling:
    """An automatic edge weapon that sprays cannonballs toward the arena."""

    def __init__(self, side: str):
        self.side = side
        self.base = pygame.Vector2(0 if side == "left" else WIDTH, HEIGHT * 0.5)

    def fire(self, aim_angle_deg: float, power: int) -> Projectile:
        # Mirror the horizontal component for the right-hand mount and add
        # per-round barrel spread.
        spray_angle = math.radians(
            aim_angle_deg
            + random.uniform(-GATLING_SPRAY_DEGREES, GATLING_SPRAY_DEGREES)
        )
        horizontal = 1 if self.side == "left" else -1
        velocity = pygame.Vector2(
            horizontal * math.cos(spray_angle),
            math.sin(spray_angle),
        ) * random.uniform(power * 0.9, power * 1.1)
        return Projectile(self.base.copy(), velocity, self.side)

    def draw(self, surface: pygame.Surface, aim_angle_deg: float) -> None:
        horizontal = 1 if self.side == "left" else -1
        angle = math.radians(aim_angle_deg)
        inward = pygame.Vector2(horizontal * math.cos(angle), math.sin(angle))
        mount_center = self.base + inward * 13
        pygame.draw.circle(surface, (70, 74, 78), self.base, 30)
        pygame.draw.circle(surface, CANNON_COLOR, mount_center, 18)
        # Multiple parallel barrels make these visually distinct from the
        # turn-based cannons on the ground.
        perpendicular = pygame.Vector2(-inward.y, inward.x)
        for offset in (-7, 0, 7):
            start = mount_center + perpendicular * offset
            end = start + inward * 48
            pygame.draw.line(surface, CANNON_COLOR, start, end, 5)


class Game:
    def __init__(self):
        pygame.init()
        global WIDTH, HEIGHT, GROUND_Y

        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        WIDTH, HEIGHT = self.screen.get_size()
        GROUND_Y = HEIGHT - 40
        set_ground_y(GROUND_Y)
        set_screen_width(WIDTH)
        pygame.display.set_caption("Caterpillar Fall")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("menlo", 24)

        self.castle_rows = 12
        self.castle_cols = 16
        castle_margin = 70
        self.left_castle_start_x = castle_margin
        self.right_castle_start_x = WIDTH - castle_margin - self.castle_cols * 34

        self.left_blocks = self._build_castle("left", self.left_castle_start_x)
        self.right_blocks = self._build_castle("right", self.right_castle_start_x)
        self.blocks = self.left_blocks + self.right_blocks

        self.left_caterpillar = self._build_castle_caterpillar("left", self.left_castle_start_x)
        self.right_caterpillar = self._build_castle_caterpillar("right", self.right_castle_start_x)
        self.caterpillars = [self.left_caterpillar, self.right_caterpillar]

        self.left_cannon = Cannon("left", 40)
        self.right_cannon = Cannon("right", WIDTH - 40)
        self.gatlings = (Gatling("left"), Gatling("right"))

        self.projectiles: list[Projectile] = []
        self.physics = PhysicsEngine(self.blocks, self.caterpillars)
        self.winner = None
        self.castle_heal_timer = CASTLE_HEAL_INTERVAL
        self.paused = False
        self.options_open = False
        self.damage_option_index = 0
        self.radius_option_index = 3
        self.impact_force_option_index = 3
        self.splash_force_option_index = 3
        self.splash_nudge_option_index = 3
        self.cannon_rain_enabled = False
        self.cannon_rain_speed_option_index = 0
        self.cannon_rain_timer = self._next_cannon_rain_interval()
        self.tornado_enabled = False
        self.tornado = Tornado()
        self.gatling_fire_rate_option_index = 1
        self.gatling_interval_option_index = 3
        self.gatling_aim_option_index = 6
        self.gatling_power_option_index = 4
        self.gatling_timer = self._next_gatling_interval()
        self.gatling_rounds_remaining = 0
        self.gatling_shot_timer = 0.0
        self.selected_option_index = 0
        self.current_turn = "left"
        self.turn_timer = TURN_TIME_LIMIT

    def _next_cannon_rain_interval(self) -> float:
        """Return a fresh delay so the rain does not settle into a rhythm."""
        random_interval = random.uniform(CANNON_RAIN_MIN_INTERVAL, CANNON_RAIN_MAX_INTERVAL)
        return random_interval / self.cannon_rain_speed

    def _spawn_raining_cannon_ball(self):
        """Drop a neutral cannon ball at a random point across the battlefield."""
        margin = 12
        x = random.randint(margin, max(margin, WIDTH - margin))
        velocity = pygame.Vector2(
            random.uniform(-55, 55),
            random.uniform(CANNON_RAIN_MIN_FALL_SPEED, CANNON_RAIN_MAX_FALL_SPEED),
        )
        self.projectiles.append(Projectile(pygame.Vector2(x, -10), velocity, "rain"))

    def _next_gatling_interval(self) -> float:
        minimum, maximum = self.gatling_interval
        return random.uniform(minimum, maximum)

    def _update_gatlings(self, dt: float) -> None:
        if self.gatling_rounds_remaining == 0:
            self.gatling_timer -= dt
            if self.gatling_timer <= 0:
                self.gatling_rounds_remaining = GATLING_BURST_SIZE
                self.gatling_shot_timer = 0.0
                # Schedule from the end of this burst rather than allowing a
                # long burst to consume the next random waiting interval.
                self.gatling_timer = self._next_gatling_interval()

        if self.gatling_rounds_remaining:
            self.gatling_shot_timer -= dt
            shot_interval = 1.0 / self.gatling_fire_rate
            while self.gatling_shot_timer <= 0 and self.gatling_rounds_remaining:
                for gatling in self.gatlings:
                    self.projectiles.append(gatling.fire(self.gatling_aim_angle, self.gatling_power))
                self.gatling_rounds_remaining -= 1
                self.gatling_shot_timer += shot_interval

    def reset_game(self):
        self.left_blocks = self._build_castle("left", self.left_castle_start_x)
        self.right_blocks = self._build_castle("right", self.right_castle_start_x)
        self.blocks = self.left_blocks + self.right_blocks

        self.left_caterpillar = self._build_castle_caterpillar("left", self.left_castle_start_x)
        self.right_caterpillar = self._build_castle_caterpillar("right", self.right_castle_start_x)
        self.caterpillars = [self.left_caterpillar, self.right_caterpillar]

        self.left_cannon = Cannon("left", 40)
        self.right_cannon = Cannon("right", WIDTH - 40)
        self.gatlings = (Gatling("left"), Gatling("right"))

        self.projectiles = []
        self.physics = PhysicsEngine(self.blocks, self.caterpillars)
        self.winner = None
        self.castle_heal_timer = CASTLE_HEAL_INTERVAL
        self.paused = False
        self.options_open = False
        self.current_turn = "left"
        self.turn_timer = TURN_TIME_LIMIT
        self.cannon_rain_timer = self._next_cannon_rain_interval()
        self.tornado = Tornado()
        self.gatling_timer = self._next_gatling_interval()
        self.gatling_rounds_remaining = 0
        self.gatling_shot_timer = 0.0

    def _build_castle(self, side: str, start_x: int):
        block_w = 34
        block_h = 24
        block_rect_h = block_h - 2
        cols = self.castle_cols
        blocks = []
        # Rows are counted from the ground upward.  The silhouette is a proper
        # fortified castle: broad foundations, two tall corner towers with
        # window openings, a lower central keep, and alternating battlements.
        # The open room in the keep shelters the caterpillar on a block seat.
        occupied_cells = set()
        occupied_cells.update((row, col) for row in range(2) for col in range(cols))

        tower_columns = tuple(range(4)) + tuple(range(cols - 4, cols))
        occupied_cells.update((row, col) for row in range(2, 11) for col in tower_columns)

        # Narrow arrow-slit windows break up the otherwise solid corner towers.
        for row in (5, 6):
            occupied_cells.discard((row, 1))
            occupied_cells.discard((row, cols - 2))

        # The central keep has two-block-thick walls and a solid parapet roof.
        occupied_cells.update((row, col) for row in range(2, 9) for col in (4, 5, cols - 6, cols - 5))
        occupied_cells.update((8, col) for col in range(4, cols - 4))

        # Merlons along both tower tops and the keep roof make the outline read
        # as a castle even when some blocks have already been knocked loose.
        occupied_cells.update((11, col) for col in tower_columns if col % 2 == 0)
        occupied_cells.update((9, col) for col in range(4, cols - 4) if col % 2 == 0)
        occupied_cells.add((2, self._castle_seat_col(side)))

        for row, col in sorted(occupied_cells):
            x = start_x + col * block_w
            y = GROUND_Y - block_rect_h - row * block_h
            blocks.append(CastleBlock(pygame.Rect(x, y, block_w - 2, block_rect_h), side))
        return blocks

    def _castle_seat_col(self, side: str) -> int:
        return 7 if side == "left" else self.castle_cols - 8

    def _build_castle_caterpillar(self, side: str, start_x: int) -> Caterpillar:
        block_w = 34
        block_h = 24
        seat_col = self._castle_seat_col(side)
        x = start_x + seat_col * block_w - 1
        # The seat occupies row two, immediately above the foundation.
        y = GROUND_Y - 3 * block_h - 24
        return Caterpillar(x, y, side)

    def _projectile_hits(self, proj: Projectile):
        target_side = None if proj.owner == "rain" else ("right" if proj.owner == "left" else "left")
        hit_point = pygame.Vector2(proj.body.rect.center)

        # Player shots hit only the enemy castle; neutral rain can hit either.
        for block in self.blocks:
            if not block.body.active:
                continue
            if target_side is not None and block.side != target_side:
                continue
            if proj.body.rect.colliderect(block.body.rect):
                block.apply_impact(self.damage_per_shot)
                block.body.vel += proj.body.vel * (
                    self.impact_force * proj.body.mass / max(1.0, block.body.mass)
                )

                for nearby in self.blocks:
                    if not nearby.body.active:
                        continue
                    if nearby.side != block.side or nearby is block:
                        continue
                    distance = hit_point.distance_to(nearby.body.center_vec())
                    if distance < self.splash_radius:
                        splash = max(0.0, (self.splash_radius - distance) * self.splash_force)
                        nearby.apply_impact(self.damage_per_shot)
                        nudge = nearby.body.center_vec() - hit_point
                        if nudge.length_squared() > 0:
                            nearby.body.vel += nudge.normalize() * (splash * self.splash_nudge)
                proj.alive = False
                return

        if proj.body.rect.bottom >= GROUND_Y:
            proj.alive = False

    def update(self, dt: float):
        if self.winner:
            return

        self.turn_timer -= dt
        if self.turn_timer <= 0:
            self._advance_turn()

        if self.cannon_rain_enabled:
            self.cannon_rain_timer -= dt
            while self.cannon_rain_timer <= 0:
                self._spawn_raining_cannon_ball()
                self.cannon_rain_timer += self._next_cannon_rain_interval()

        self._update_gatlings(dt)

        if self.tornado_enabled:
            self.tornado.update(dt, self.blocks, self.projectiles)

        for proj in self.projectiles:
            proj.update(dt)
            self._projectile_hits(proj)
        self.projectiles = [p for p in self.projectiles if p.alive]
        self._despawn_destroyed_blocks()

        self.physics.update(dt)

        self.castle_heal_timer -= dt
        while self.castle_heal_timer <= 0:
            self._heal_castles()
            self.castle_heal_timer += CASTLE_HEAL_INTERVAL

        if self.left_caterpillar.fallen:
            self.winner = "Right"
        elif self.right_caterpillar.fallen:
            self.winner = "Left"

    def _active_cannon(self) -> Cannon:
        if self.current_turn == "left":
            return self.left_cannon
        return self.right_cannon

    @property
    def damage_per_shot(self) -> int:
        return DAMAGE_OPTIONS[self.damage_option_index][1]

    @property
    def damage_option_name(self) -> str:
        return DAMAGE_OPTIONS[self.damage_option_index][0]

    @property
    def splash_radius(self) -> int:
        return RADIUS_OPTIONS[self.radius_option_index]

    @property
    def impact_force(self) -> float:
        return IMPACT_FORCE_OPTIONS[self.impact_force_option_index]

    @property
    def splash_force(self) -> float:
        return SPLASH_FORCE_OPTIONS[self.splash_force_option_index]

    @property
    def splash_nudge(self) -> float:
        return SPLASH_NUDGE_OPTIONS[self.splash_nudge_option_index]

    @property
    def cannon_rain_speed(self) -> int:
        return CANNON_RAIN_SPEED_OPTIONS[self.cannon_rain_speed_option_index]

    @property
    def gatling_fire_rate(self) -> int:
        return GATLING_FIRE_RATE_OPTIONS[self.gatling_fire_rate_option_index]

    @property
    def gatling_interval(self) -> tuple[int, int]:
        return GATLING_INTERVAL_OPTIONS[self.gatling_interval_option_index]

    @property
    def gatling_aim_angle(self) -> int:
        return GATLING_AIM_OPTIONS[self.gatling_aim_option_index]

    @property
    def gatling_power(self) -> int:
        return GATLING_POWER_OPTIONS[self.gatling_power_option_index]

    def adjust_selected_option(self, direction: int):
        option_attributes = (
            ("damage_option_index", DAMAGE_OPTIONS),
            ("radius_option_index", RADIUS_OPTIONS),
            ("impact_force_option_index", IMPACT_FORCE_OPTIONS),
            ("splash_force_option_index", SPLASH_FORCE_OPTIONS),
            ("splash_nudge_option_index", SPLASH_NUDGE_OPTIONS),
            ("cannon_rain_enabled", (False, True)),
            ("cannon_rain_speed_option_index", CANNON_RAIN_SPEED_OPTIONS),
            ("tornado_enabled", (False, True)),
            ("gatling_fire_rate_option_index", GATLING_FIRE_RATE_OPTIONS),
            ("gatling_interval_option_index", GATLING_INTERVAL_OPTIONS),
            ("gatling_aim_option_index", GATLING_AIM_OPTIONS),
            ("gatling_power_option_index", GATLING_POWER_OPTIONS),
        )
        attribute, values = option_attributes[self.selected_option_index]
        if attribute in ("cannon_rain_enabled", "tornado_enabled"):
            setattr(self, attribute, not getattr(self, attribute))
            if attribute == "cannon_rain_enabled":
                self.cannon_rain_timer = self._next_cannon_rain_interval()
            return
        setattr(self, attribute, (getattr(self, attribute) + direction) % len(values))
        if attribute == "cannon_rain_speed_option_index":
            self.cannon_rain_timer = self._next_cannon_rain_interval()
        elif attribute == "gatling_interval_option_index" and not self.gatling_rounds_remaining:
            self.gatling_timer = self._next_gatling_interval()

    def _advance_turn(self):
        self.current_turn = "right" if self.current_turn == "left" else "left"
        self.turn_timer = TURN_TIME_LIMIT

    def adjust_active_cannon(self, aim_delta: float = 0.0, speed_delta: float = 0.0):
        cannon = self._active_cannon()
        if aim_delta:
            cannon.adjust_aim(aim_delta)
        if speed_delta:
            cannon.adjust_speed(speed_delta)

    def fire_active_cannon(self):
        if self.winner or self.paused:
            return
        self.projectiles.append(self._active_cannon().fire())
        self._advance_turn()

    def _despawn_destroyed_blocks(self):
        self.blocks[:] = [block for block in self.blocks if block.body.active]
        self.left_blocks[:] = [block for block in self.left_blocks if block.body.active]
        self.right_blocks[:] = [block for block in self.right_blocks if block.body.active]

    def _heal_castles(self):
        """Repair every surviving castle block by one current shot's damage."""
        for block in self.blocks:
            block.heal(self.damage_per_shot)

    def draw(self):
        self.screen.fill(SKY)
        pygame.draw.rect(self.screen, GROUND, (0, GROUND_Y, WIDTH, HEIGHT - GROUND_Y))

        if self.tornado_enabled:
            self.tornado.draw(self.screen)

        for block in self.blocks:
            self.screen.blit(block.sprite, block.body.rect.topleft)

        self.left_cannon.draw(self.screen)
        self.right_cannon.draw(self.screen)
        for gatling in self.gatlings:
            gatling.draw(self.screen, self.gatling_aim_angle)

        for cannon in (self.left_cannon, self.right_cannon):
            tracer = cannon.tracer_points()
            if len(tracer) > 1:
                color = LEFT_COLOR if cannon.side == "left" else RIGHT_COLOR
                pygame.draw.lines(self.screen, color, False, tracer, 2)

        for proj in self.projectiles:
            pygame.draw.circle(self.screen, PROJECTILE_COLOR, proj.body.rect.center, 5)

        self.left_caterpillar.draw(self.screen)
        self.right_caterpillar.draw(self.screen)

        caption = "Caterpillar Fall · One shot per turn · Castle blocks heal every 30s"
        self.screen.blit(self.font.render(caption, True, TEXT_COLOR), (24, 16))
        pause_hint = "Controls: Up/Down aim, Left/Right power, Space fire, P pause, O options, R restart"
        self.screen.blit(self.font.render(pause_hint, True, TEXT_COLOR), (24, 46))
        turn_text = f"Turn: {self.current_turn.title()}  |  Time left: {max(0.0, self.turn_timer):04.1f}s"
        self.screen.blit(self.font.render(turn_text, True, TEXT_COLOR), (24, 76))
        speed_text = (
            f"Left speed {int(self.left_cannon.muzzle_speed)}  |  Right speed {int(self.right_cannon.muzzle_speed)}"
        )
        self.screen.blit(self.font.render(speed_text, True, TEXT_COLOR), (24, 106))
        if self.paused:
            paused_text = self.font.render("Paused", True, (180, 30, 30))
            self.screen.blit(paused_text, (WIDTH // 2 - paused_text.get_width() // 2, 136))
        if self.winner:
            msg = f"{self.winner} side wins!"
            text = self.font.render(msg, True, (180, 30, 30))
            self.screen.blit(text, (WIDTH // 2 - text.get_width() // 2, 166))

        if self.options_open:
            self._draw_options_menu()

        pygame.display.flip()

    def _draw_options_menu(self):
        menu_width = min(700, WIDTH - 80)
        menu_height = min(574, HEIGHT - 40)
        menu_rect = pygame.Rect(0, 0, menu_width, menu_height)
        menu_rect.center = (WIDTH // 2, HEIGHT // 2)

        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 105))
        self.screen.blit(overlay, (0, 0))
        panel = pygame.Surface(menu_rect.size, pygame.SRCALPHA)
        panel.fill(MENU_BACKDROP)
        self.screen.blit(panel, menu_rect.topleft)
        pygame.draw.rect(self.screen, MENU_HIGHLIGHT, menu_rect, 3, border_radius=8)

        title = self.font.render("Options", True, (255, 255, 255))
        self.screen.blit(title, (menu_rect.centerx - title.get_width() // 2, menu_rect.top + 28))

        option_texts = (
            f"Damage multiplier  <  {self.damage_option_name} ({self.damage_per_shot}x)  >",
            f"Splash radius      <  {self.splash_radius} px  >",
            f"Impact force       <  {self.impact_force:.2f}x  >",
            f"Splash force       <  {self.splash_force:.2f}x  >",
            f"Splash nudge       <  {self.splash_nudge:.2f}x  >",
            f"Cannon ball rain   <  {'On' if self.cannon_rain_enabled else 'Off'}  >",
            f"Rain rate speed    <  {self.cannon_rain_speed}x  >",
            f"Center tornado     <  {'On' if self.tornado_enabled else 'Off'}  >",
            f"Gatling fire rate  <  {self.gatling_fire_rate} rounds/s  >",
            f"Gatling interval   <  {self.gatling_interval[0]}-{self.gatling_interval[1]} s  >",
            f"Gatling aim        <  {self.gatling_aim_angle:+d} deg  >",
            f"Gatling power      <  {self.gatling_power} px/s  >",
        )
        for index, option_text in enumerate(option_texts):
            color = MENU_HIGHLIGHT if index == self.selected_option_index else (225, 225, 225)
            prefix = "> " if index == self.selected_option_index else "  "
            option = self.font.render(prefix + option_text, True, color)
            row_spacing = min(48, (menu_rect.height - 178) // len(option_texts))
            self.screen.blit(
                option,
                (menu_rect.centerx - option.get_width() // 2, menu_rect.top + 82 + index * row_spacing),
            )

        hint = self.font.render("Up/Down select · Left/Right change · O or Esc close", True, (225, 225, 225))
        self.screen.blit(hint, (menu_rect.centerx - hint.get_width() // 2, menu_rect.bottom - 58))

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    if self.options_open:
                        self.options_open = False
                    else:
                        running = False
                if event.type == pygame.KEYDOWN and event.key == pygame.K_o:
                    self.options_open = not self.options_open
                if event.type == pygame.KEYDOWN and self.options_open:
                    if event.key == pygame.K_LEFT:
                        self.adjust_selected_option(-1)
                    elif event.key == pygame.K_RIGHT:
                        self.adjust_selected_option(1)
                    elif event.key == pygame.K_UP:
                        self.selected_option_index = (
                            self.selected_option_index - 1
                        ) % OPTION_MENU_COUNT
                    elif event.key == pygame.K_DOWN:
                        self.selected_option_index = (
                            self.selected_option_index + 1
                        ) % OPTION_MENU_COUNT
                if event.type == pygame.KEYDOWN and event.key == pygame.K_p:
                    if not self.options_open:
                        self.paused = not self.paused
                if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                    if not self.options_open:
                        self.fire_active_cannon()
                if event.type == pygame.KEYDOWN and event.key == pygame.K_r and self.winner:
                    self.reset_game()

            if not self.paused and not self.options_open:
                keys = pygame.key.get_pressed()
                aim_speed_deg = 55 * dt
                power_speed = 480 * dt
                if keys[pygame.K_UP]:
                    self.adjust_active_cannon(aim_delta=aim_speed_deg)
                if keys[pygame.K_DOWN]:
                    self.adjust_active_cannon(aim_delta=-aim_speed_deg)
                if keys[pygame.K_RIGHT]:
                    self.adjust_active_cannon(speed_delta=power_speed)
                if keys[pygame.K_LEFT]:
                    self.adjust_active_cannon(speed_delta=-power_speed)
                self.update(dt)
            self.draw()

        pygame.quit()


if __name__ == "__main__":
    Game().run()
