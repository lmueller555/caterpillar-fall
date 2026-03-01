import random
from dataclasses import dataclass
from typing import Any

import pygame


GRAVITY = 900.0  # px/s^2
PHYSICS_SUBSTEPS = 5
GROUND_Y = 680


def set_ground_y(y: int) -> None:
    global GROUND_Y
    GROUND_Y = y


@dataclass
class Body:
    rect: pygame.Rect
    vel: pygame.Vector2
    mass: float
    dynamic: bool = True
    active: bool = True

    def center_vec(self) -> pygame.Vector2:
        return pygame.Vector2(self.rect.centerx, self.rect.centery)


class PhysicsEngine:
    def __init__(self, blocks: list[Any], caterpillars: list[Any]):
        self.blocks = blocks
        self.caterpillars = caterpillars

    @staticmethod
    def _horizontal_overlap(a: pygame.Rect, b: pygame.Rect) -> int:
        return max(0, min(a.right, b.right) - max(a.left, b.left))

    def _is_supported(self, block: Any) -> bool:
        body = block.body
        if not body.active:
            return False
        if body.rect.bottom >= GROUND_Y:
            return True

        support_gap_px = 3
        for other in self.blocks:
            if other is block or not other.body.active:
                continue
            if self._horizontal_overlap(body.rect, other.body.rect) < 6:
                continue

            vertical_gap = other.body.rect.top - body.rect.bottom
            if 0 <= vertical_gap <= support_gap_px:
                return True
        return False

    def _resolve_block_collisions(self, block: Any, move_x: float, move_y: float):
        body = block.body
        if not body.active:
            return
        for other in self.blocks:
            if other is block or not other.body.active or not body.rect.colliderect(other.body.rect):
                continue

            overlap = body.rect.clip(other.body.rect)
            if overlap.width <= 0 or overlap.height <= 0:
                continue

            if overlap.width < overlap.height:
                if move_x > 0:
                    body.rect.right = other.body.rect.left
                elif move_x < 0:
                    body.rect.left = other.body.rect.right
                else:
                    body.rect.x += -overlap.width if body.rect.centerx < other.body.rect.centerx else overlap.width
                body.vel.x = 0
            else:
                if move_y > 0:
                    body.rect.bottom = other.body.rect.top

                    support_width = self._horizontal_overlap(body.rect, other.body.rect)
                    support_ratio = support_width / max(1, body.rect.width)
                    if support_ratio < 0.6:
                        support_center = (
                            max(body.rect.left, other.body.rect.left) + min(body.rect.right, other.body.rect.right)
                        ) * 0.5
                        direction = 1 if support_center < body.rect.centerx else -1
                        body.vel.x += direction * (220 * (0.6 - support_ratio))
                elif move_y < 0:
                    body.rect.top = other.body.rect.bottom
                else:
                    body.rect.y += -overlap.height if body.rect.centery < other.body.rect.centery else overlap.height
                body.vel.y = 0

    def _resolve_caterpillar_collisions(self, caterpillar: Any, move_x: float, move_y: float):
        body = caterpillar.body
        for block in self.blocks:
            if not block.body.active:
                continue
            if not body.rect.colliderect(block.body.rect):
                continue

            overlap = body.rect.clip(block.body.rect)
            if overlap.width <= 0 or overlap.height <= 0:
                continue

            if overlap.width < overlap.height:
                if move_x > 0:
                    body.rect.right = block.body.rect.left
                elif move_x < 0:
                    body.rect.left = block.body.rect.right
                else:
                    body.rect.x += -overlap.width if body.rect.centerx < block.body.rect.centerx else overlap.width
                body.vel.x = 0
            else:
                if move_y > 0:
                    body.rect.bottom = block.body.rect.top
                elif move_y < 0:
                    body.rect.top = block.body.rect.bottom
                else:
                    body.rect.y += -overlap.height if body.rect.centery < block.body.rect.centery else overlap.height
                body.vel.y = 0

    def update(self, dt: float):
        for block in self.blocks:
            if not block.body.active:
                continue
            if not block.body.dynamic and not self._is_supported(block):
                block.body.dynamic = True

        step_dt = dt / PHYSICS_SUBSTEPS
        for _ in range(PHYSICS_SUBSTEPS):
            for block in self.blocks:
                body = block.body
                if not body.active or not body.dynamic:
                    continue

                body.vel.y += GRAVITY * step_dt

                dx = body.vel.x * step_dt
                body.rect.x += int(round(dx))
                self._resolve_block_collisions(block, dx, 0)

                dy = body.vel.y * step_dt
                body.rect.y += int(round(dy))

                if body.rect.bottom >= GROUND_Y:
                    body.rect.bottom = GROUND_Y
                    body.vel.y = 0
                    body.vel.x *= 0.82

                self._resolve_block_collisions(block, 0, dy)

                if body.rect.bottom >= GROUND_Y - 1:
                    body.vel.x *= 0.9
                else:
                    body.vel.x *= 0.995

                if abs(body.vel.x) < 2:
                    body.vel.x = 0

        for caterpillar in self.caterpillars:
            if caterpillar.body.dynamic:
                step_dt = dt / PHYSICS_SUBSTEPS
                for _ in range(PHYSICS_SUBSTEPS):
                    caterpillar.body.vel.y += GRAVITY * step_dt

                    dx = caterpillar.body.vel.x * step_dt
                    caterpillar.body.rect.x += int(round(dx))
                    self._resolve_caterpillar_collisions(caterpillar, dx, 0)

                    dy = caterpillar.body.vel.y * step_dt
                    caterpillar.body.rect.y += int(round(dy))
                    self._resolve_caterpillar_collisions(caterpillar, 0, dy)

                    if caterpillar.body.rect.bottom >= GROUND_Y:
                        caterpillar.body.rect.bottom = GROUND_Y
                        caterpillar.body.vel.update(0, 0)
                        caterpillar.fallen = True
                        break
                continue

            supporting = False
            feet = caterpillar.body.rect.move(0, 4)
            for block in self.blocks:
                if not block.body.active:
                    continue
                if block.side != caterpillar.side:
                    continue
                if block.body.rect.colliderect(feet):
                    supporting = True
                    break
            if not supporting:
                caterpillar.body.dynamic = True
                caterpillar.body.vel = pygame.Vector2(random.uniform(-30, 30), -20)
