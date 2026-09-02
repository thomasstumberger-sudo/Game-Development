/** 
 * Resource and tribe HUD.
 *
 * Seed-level: drawn on the canvas (never DOM widgets), positioned in screen
 * space rather than world space, and legible. The carved-bone / woad-stain
 * treatment called for in the brief is left for the build to develop.
 *
 * Pure module: no DOM, no side effects on import.
 */

import { PALETTE } from './palette.js';
import { RESOURCE_FEEDBACK } from './state.js';
import { hexToPixel } from './hex.js';

const ROW = [
    { key: 'food', label: 'Food', color: PALETTE.FOOD },
    { key: 'water', label: 'Water', color: PALETTE.WATER_RES },
    { key: 'morale', label: 'Morale', color: PALETTE.MORALE },
    { key: 'magic', label: 'Magic', color: PALETTE.MAGIC },
    { key: 'population', label: 'Tribe', color: PALETTE.POPULATION },
];

function createHUDTexture(ctx, width, height) {
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const textureCtx = canvas.getContext('2d');
    
    // Fill with base color
    textureCtx.fillStyle = PALETTE.BROWN_DARKER;
    textureCtx.fillRect(0, 0, width, height);
    
    // Add carved bone texture pattern - more pronounced for better visual effect
    textureCtx.globalCompositeOperation = 'overlay';
    textureCtx.strokeStyle = PALETTE.BROWN_MEDIUM;
    textureCtx.lineWidth = 1.2;
    for (let i = 0; i < 50; i++) {
      const x1 = Math.random() * width;
      const y1 = Math.random() * height;
      const x2 = x1 + (Math.random() - 0.5) * 30;
      const y2 = y1 + (Math.random() - 0.5) * 30;
      textureCtx.beginPath();
      textureCtx.moveTo(x1, y1);
      textureCtx.lineTo(x2, y2);
      textureCtx.stroke();
    }
    
    // Add some woad-stain style patterns
    textureCtx.globalCompositeOperation = 'source-over';
    textureCtx.fillStyle = PALETTE.BROWN_DARK;
    for (let i = 0; i < 30; i++) {
      const x = Math.random() * width;
      const y = Math.random() * height;
      const radius = Math.random() * 4 + 1;
      textureCtx.beginPath();
      textureCtx.arc(x, y, radius, 0, Math.PI * 2);
      textureCtx.fill();
    }
    
    // Add subtle texture for depth - more pronounced
    textureCtx.globalCompositeOperation = 'source-over';
    textureCtx.strokeStyle = PALETTE.BROWN_DARKER;
    textureCtx.lineWidth = 0.7;
    for (let i = 0; i < 25; i++) {
      const x1 = Math.random() * width;
      const y1 = Math.random() * height;
      const x2 = x1 + (Math.random() - 0.5) * 12;
      const y2 = y1 + (Math.random() - 0.5) * 12;
      textureCtx.beginPath();
      textureCtx.moveTo(x1, y1);
      textureCtx.lineTo(x2, y2);
      textureCtx.stroke();
    }
    
    // Add some more detailed patterns for better texture
    textureCtx.globalCompositeOperation = 'source-over';
    textureCtx.strokeStyle = PALETTE.BROWN_DARK;
    textureCtx.lineWidth = 0.5;
    for (let i = 0; i < 20; i++) {
      const x1 = Math.random() * width;
      const y1 = Math.random() * height;
      const x2 = x1 + (Math.random() - 0.5) * 8;
      const y2 = y1 + (Math.random() - 0.5) * 8;
      textureCtx.beginPath();
      textureCtx.moveTo(x1, y1);
      textureCtx.lineTo(x2, y2);
      textureCtx.stroke();
    }
    
    // Add additional carved patterns for more authenticity
    textureCtx.globalCompositeOperation = 'source-over';
    textureCtx.strokeStyle = PALETTE.BROWN_DARK;
    textureCtx.lineWidth = 0.8;
    for (let i = 0; i < 15; i++) {
      const x = Math.random() * width;
      const y = Math.random() * height;
      const len = Math.random() * 20 + 10;
      const angle = Math.random() * Math.PI * 2;
      textureCtx.beginPath();
      textureCtx.moveTo(x, y);
      textureCtx.lineTo(x + Math.cos(angle) * len, y + Math.sin(angle) * len);
      textureCtx.stroke();
    }
    
    return canvas;
}

function panel(ctx, x, y, w, h) {
    // Create texture for the panel
    const texture = createHUDPanelTexture(ctx, w, h);
    ctx.fillStyle = ctx.createPattern(texture, 'repeat');
    ctx.globalAlpha = 0.92;
    ctx.fillRect(x, y, w, h);
    ctx.globalAlpha = 1;
    ctx.strokeStyle = PALETTE.UI_BORDER;
    ctx.lineWidth = 2.5;
    ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
}

function drawTextWithStroke(ctx, text, x, y, font, fillStyle, strokeStyle, strokeWidth) {
    ctx.font = font;
    ctx.strokeStyle = strokeStyle;
    ctx.lineWidth = strokeWidth;
    ctx.strokeText(text, x, y);
    ctx.fillStyle = fillStyle;
    ctx.fillText(text, x, y);
}

/** 
 * @param {CanvasRenderingContext2D} ctx
 * @param {object} state
 */
export function drawHud(ctx, state) {
    // Safety check for null state or unit
    if (!state || !state.unit) return;
    
    const { resources, turn } = state;
    
    ctx.save();
    ctx.textBaseline = 'middle';
    
    // --- resource bar across the top ---------------------------------------
    const barH = 48;
    panel(ctx, 0, 0, state.width, barH);
    
    // Draw resource labels and values
    const labelW = 70;
    const labelH = 20;
    const labelY = barH / 2;
    
    for (let i = 0; i < ROW.length; i++) {
        const { key, label, color } = ROW[i];
        const x = 10 + i * labelW;
        
        // Draw background
        ctx.fillStyle = PALETTE.BROWN_DARKER;
        ctx.fillRect(x, 5, labelW - 10, labelH);
        
        // Draw border
        ctx.strokeStyle = PALETTE.UI_BORDER;
        ctx.lineWidth = 1;
        ctx.strokeRect(x + 0.5, 5.5, labelW - 10, labelH - 1);
        
        // Draw label
        ctx.font = 'bold 12px "Courier New", monospace';
        ctx.fillStyle = PALETTE.PARCHMENT;
        ctx.textAlign = 'center';
        ctx.fillText(label, x + labelW / 2, labelY - 5);
        
        // Draw value
        ctx.font = 'bold 14px "Courier New", monospace';
        ctx.fillStyle = color;
        ctx.fillText(resources[key], x + labelW / 2, labelY + 5);
    }
    
    // --- turn counter --------------------------------------------------------
    const turnX = state.width - 100;
    const turnY = barH / 2;
    
    ctx.font = 'bold 16px "Courier New", monospace';
    ctx.fillStyle = PALETTE.PARCHMENT;
    ctx.textAlign = 'right';
    ctx.fillText(`Turn ${turn}`, turnX, turnY);
    
    // --- tribe roster --------------------------------------------------------
    const rosterW = 200;
    const rosterH = 150;
    const rosterX = state.width - rosterW - 10;
    const rosterY = barH + 10;
    
    panel(ctx, rosterX, rosterY, rosterW, rosterH);
    
    // Draw title
    ctx.font = 'bold 14px "Courier New", monospace';
    ctx.fillStyle = PALETTE.PARCHMENT;
    ctx.textAlign = 'center';
    ctx.fillText('TRIBE', rosterX + 15, rosterY + 20);
    
    // Draw tribe members with better visual distinction
    const memberHeight = 25;
    const memberY = rosterY + 40;
    const roleWidth = 60;
    
    // Sample tribe members - in a real game this would come from state
    const tribeMembers = [
        { name: 'Yarrow', role: 'shaman', health: 10, maxHealth: 10 },
        { name: 'Torc', role: 'warrior', health: 8, maxHealth: 10 },
        { name: 'Wren', role: 'scout', health: 9, maxHealth: 10 },
        { name: 'Dunn', role: 'craftsman', health: 7, maxHealth: 10 },
    ];
    
    for (let i = 0; i < Math.min(4, tribeMembers.length); i++) {
        const member = tribeMembers[i];
        const y = memberY + i * memberHeight;
        
        // Draw role with color coding and icon
        ctx.font = '12px "Courier New", monospace';
        ctx.fillStyle = PALETTE.PARCHMENT;
        ctx.textAlign = 'left';
        
        // Draw role name with icon
        const roleName = member.role.toUpperCase();
        drawRoleMarker(ctx, rosterX + 10, y, member.role, 8); // Draw the role marker first
        ctx.fillText(roleName, rosterX + 25, y);
        
        // Draw health bar for the member
        const healthBarX = rosterX + roleWidth + 20;
        const healthBarY = y - 5;
        const healthBarWidth = 40;
        const healthBarHeight = 8;
        
        // Background
        ctx.fillStyle = PALETTE.BROWN_DARKER;
        ctx.fillRect(healthBarX, healthBarY, healthBarWidth, healthBarHeight);
        
        // Border
        ctx.strokeStyle = PALETTE.BROWN_MEDIUM;
        ctx.lineWidth = 0.5;
        ctx.strokeRect(healthBarX, healthBarY, healthBarWidth, healthBarHeight);
        
        // Health fill
        const healthPercent = member.health / member.maxHealth;
        ctx.fillStyle = healthPercent > 0.5 ? '#4caf50' : (healthPercent > 0.25 ? '#ff9800' : '#f44336');
        ctx.fillRect(healthBarX, healthBarY, healthBarWidth * healthPercent, healthBarHeight);
        
        // Draw member name
        ctx.font = '12px "Courier New", monospace';
        ctx.fillStyle = PALETTE.PARCHMENT;
        ctx.textAlign = 'left';
        ctx.fillText(member.name, rosterX + roleWidth + 70, y);
    }
    
    // --- resource feedback ---------------------------------------------------
    // This used to call RESOURCE_FEEDBACK.draw(), a method that never existed;
    // the TypeError was caught and logged as a warning 60 times a second, which
    // is why the console-error gate never noticed. The drawing belongs here
    // anyway — the feedback store holds data, the HUD renders it.
    drawResourceFeedback(ctx);

    ctx.restore();
}

/**
 * Geometry of the encounter window.
 *
 * Drawing and hit-testing derive from this one function, so an option button
 * can never be drawn somewhere the click handler is not looking. The previous
 * build split them, and the hit-tester was left permanently returning null.
 */
export function encounterLayout(state) {
    const w = Math.min(520, state.width - 80);
    const h = 260;
    const x = (state.width - w) / 2;
    const y = (state.height - h) / 2;
    const optionH = 32;
    const gap = 8;
    return {
        x, y, w, h, optionH, gap,
        optionRect(index, total) {
            return {
                x: x + 24,
                y: y + h - 24 - (total - index) * (optionH + gap),
                w: w - 48,
                h: optionH,
            };
        },
    };
}

/** @returns {number} index of the option under (px, py), or -1 */
export function encounterOptionAt(state, system, px, py) {
    if (!system?.active || !system.current) return -1;
    const layout = encounterLayout(state);
    const total = system.current.options.length;
    for (let i = 0; i < total; i++) {
        const r = layout.optionRect(i, total);
        if (px >= r.x && px <= r.x + r.w && py >= r.y && py <= r.y + r.h) return i;
    }
    return -1;
}

/** The encounter window. Drawn last, over everything, in screen space. */
export function drawEncounter(ctx, state, system) {
    if (!system?.active || !system.current) return;
    const e = system.current;
    const layout = encounterLayout(state);
    const { x, y, w, h } = layout;

    ctx.save();
    ctx.fillStyle = 'rgba(10, 8, 14, 0.72)';
    ctx.fillRect(0, 0, state.width, state.height);

    ctx.fillStyle = PALETTE.PARCHMENT;
    ctx.fillRect(x, y, w, h);
    ctx.strokeStyle = PALETTE.BROWN_DARK;
    ctx.lineWidth = 3;
    ctx.strokeRect(x, y, w, h);

    ctx.textBaseline = 'middle';
    ctx.textAlign = 'center';
    ctx.fillStyle = PALETTE.FAERY_PURPLE;
    ctx.font = 'bold 18px "Courier New", monospace';
    ctx.fillText(e.name, x + w / 2, y + 26);

    ctx.textAlign = 'left';
    ctx.fillStyle = PALETTE.BROWN_DARKER;
    ctx.font = '13px "Courier New", monospace';
    let ty = y + 56;
    for (const line of wrapText(ctx, e.description, w - 48)) {
        ctx.fillText(line, x + 24, ty);
        ty += 18;
    }

    const total = e.options.length;
    e.options.forEach((option, i) => {
        const r = layout.optionRect(i, total);
        const hot =
            state.input.mouse.x >= r.x && state.input.mouse.x <= r.x + r.w &&
            state.input.mouse.y >= r.y && state.input.mouse.y <= r.y + r.h;
        ctx.fillStyle = hot ? PALETTE.BROWN_MEDIUM : PALETTE.BROWN_DARK;
        ctx.fillRect(r.x, r.y, r.w, r.h);
        ctx.fillStyle = PALETTE.PARCHMENT;
        ctx.fillText(`${i + 1}. ${option.text}`, r.x + 12, r.y + r.h / 2);
    });

    ctx.restore();
}

function wrapText(ctx, text, maxWidth) {
    const words = text.split(' ');
    const lines = [];
    let line = words[0] ?? '';
    for (let i = 1; i < words.length; i++) {
        if (ctx.measureText(`${line} ${words[i]}`).width < maxWidth) line += ` ${words[i]}`;
        else { lines.push(line); line = words[i]; }
    }
    lines.push(line);
    return lines;
}

/**
 * Float recent resource losses above the resource bar. Entries fade out over
 * their two-second lifetime so the bar does not accumulate clutter.
 */
function drawResourceFeedback(ctx) {
    const changes = RESOURCE_FEEDBACK.getChanges();
    if (!changes.length) return;

    ctx.save();
    ctx.textAlign = 'left';
    ctx.font = 'bold 12px "Courier New", monospace';

    const now = Date.now();
    changes.forEach((change, i) => {
        const age = (now - change.time) / 2000;
        const rise = age * 14;
        ctx.globalAlpha = Math.max(0, 1 - age);
        ctx.fillStyle = change.amount < 0 ? PALETTE.MORALE : PALETTE.FOOD;
        const sign = change.amount < 0 ? '' : '+';
        ctx.fillText(`${sign}${change.amount} ${change.resource}`, 16, 62 + i * 16 - rise);
    });

    ctx.restore();
}

// Create a texture for HUD panels with carved bone and woad-stain effects
function createHUDPanelTexture(ctx, width, height) {
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const textureCtx = canvas.getContext('2d');
    
    // Fill with base color
    textureCtx.fillStyle = PALETTE.BROWN_DARKER;
    textureCtx.fillRect(0, 0, width, height);
    
    // Add carved bone texture pattern - more pronounced for better visual effect
    textureCtx.globalCompositeOperation = 'overlay';
    textureCtx.strokeStyle = PALETTE.BROWN_MEDIUM;
    textureCtx.lineWidth = 1.2;
    for (let i = 0; i < 50; i++) {
      const x1 = Math.random() * width;
      const y1 = Math.random() * height;
      const x2 = x1 + (Math.random() - 0.5) * 30;
      const y2 = y1 + (Math.random() - 0.5) * 30;
      textureCtx.beginPath();
      textureCtx.moveTo(x1, y1);
      textureCtx.lineTo(x2, y2);
      textureCtx.stroke();
    }
    
    // Add some woad-stain style patterns
    textureCtx.globalCompositeOperation = 'source-over';
    textureCtx.fillStyle = PALETTE.BROWN_DARK;
    for (let i = 0; i < 30; i++) {
      const x = Math.random() * width;
      const y = Math.random() * height;
      const radius = Math.random() * 4 + 1;
      textureCtx.beginPath();
      textureCtx.arc(x, y, radius, 0, Math.PI * 2);
      textureCtx.fill();
    }
    
    // Add subtle texture for depth - more pronounced
    textureCtx.globalCompositeOperation = 'source-over';
    textureCtx.strokeStyle = PALETTE.BROWN_DARKER;
    textureCtx.lineWidth = 0.7;
    for (let i = 0; i < 25; i++) {
      const x1 = Math.random() * width;
      const y1 = Math.random() * height;
      const x2 = x1 + (Math.random() - 0.5) * 12;
      const y2 = y1 + (Math.random() - 0.5) * 12;
      textureCtx.beginPath();
      textureCtx.moveTo(x1, y1);
      textureCtx.lineTo(x2, y2);
      textureCtx.stroke();
    }
    
    // Add some more detailed patterns for better texture
    textureCtx.globalCompositeOperation = 'source-over';
    textureCtx.strokeStyle = PALETTE.BROWN_DARK;
    textureCtx.lineWidth = 0.5;
    for (let i = 0; i < 20; i++) {
      const x1 = Math.random() * width;
      const y1 = Math.random() * height;
      const x2 = x1 + (Math.random() - 0.5) * 8;
      const y2 = y1 + (Math.random() - 0.5) * 8;
      textureCtx.beginPath();
      textureCtx.moveTo(x1, y1);
      textureCtx.lineTo(x2, y2);
      textureCtx.stroke();
    }
    
    // Add additional carved patterns for more authenticity
    textureCtx.globalCompositeOperation = 'source-over';
    textureCtx.strokeStyle = PALETTE.BROWN_DARK;
    textureCtx.lineWidth = 0.8;
    for (let i = 0; i < 15; i++) {
      const x = Math.random() * width;
      const y = Math.random() * height;
      const len = Math.random() * 20 + 10;
      const angle = Math.random() * Math.PI * 2;
      textureCtx.beginPath();
      textureCtx.moveTo(x, y);
      textureCtx.lineTo(x + Math.cos(angle) * len, y + Math.sin(angle) * len);
      textureCtx.stroke();
    }
    
    return canvas;
  }

  // Add a helper function to draw role icons in HUD
  export function drawRoleMarker(ctx, x, y, role, size = 12) {
    if (!role) return;
    
    const color = getRoleColor(role);
    const icon = getRoleIcon(role);
    
    ctx.save();
    ctx.globalAlpha = 0.95;
    
    // Draw a circle with role-specific color
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(x, y, size/2, 0, Math.PI * 2);
    ctx.fill();
    
    // Add a thick outline for better visibility
    ctx.strokeStyle = PALETTE.BACKGROUND;
    ctx.lineWidth = 2;
    ctx.stroke();
    
    // Draw role icon in the center
    ctx.fillStyle = PALETTE.PARCHMENT; // Use parchment color for better contrast
    ctx.font = `${size - 2}px "Courier New", monospace`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(icon, x, y);
    
    ctx.restore();
  }

  // Add a helper function to get role color for HUD
  export function getRoleColor(role) {
    switch (role.toLowerCase()) {
      case 'shaman':
        return PALETTE.FAERY_PURPLE;
      case 'warrior':
        return PALETTE.FAERY_GREEN;
      case 'scout':
        return PALETTE.FAERY_BLUE;
      case 'craftsman':
        return PALETTE.BROWN_MEDIUM;
      case 'hunter':
        return PALETTE.BROWN_DARKER;
      default:
        return PALETTE.PARCHMENT;
    }
  }

  // Add a helper function to get role icon for HUD
  export function getRoleIcon(role) {
    const ROLE_ICONS = {
      shaman: 'S', // Shaman symbol
      warrior: '⚔️', // Warrior weapon
      scout: '👁️', // Scout eye
      craftsman: '🔨', // Craftsman tool
      hunter: '🏹'  // Hunter bow
    };
    return ROLE_ICONS[role.toLowerCase()] || '●';
  }
