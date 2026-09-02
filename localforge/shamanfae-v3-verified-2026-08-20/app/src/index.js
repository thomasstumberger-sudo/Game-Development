/** 
 * Entry point for the game.
 */
import { initGame } from './main.js';

// Initialize the game when the page loads
const initGameWrapper = function() {
    const canvas = document.getElementById('game');
    if (canvas) {
        initGame(canvas);
    } else {
        console.error('No canvas element found with id "game"');
    }
};

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initGameWrapper);
} else {
    initGameWrapper();
}