// Simple test to check if all modules can be imported and work together
try {
    // Test that we can import all modules without errors
    import('./src/palette.js').then(() => console.log('✓ Palette imported'));
    import('./src/hex.js').then(() => console.log('✓ Hex imported'));
    import('./src/render-map.js').then(() => console.log('✓ Render map imported'));
    import('./src/render-unit.js').then(() => console.log('✓ Render unit imported'));
    import('./src/hud.js').then(() => console.log('✓ HUD imported'));
    import('./src/encounters.js').then(() => console.log('✓ Encounters imported'));
    import('./src/state.js').then(() => console.log('✓ State imported'));
    import('./src/input.js').then(() => console.log('✓ Input imported'));
    import('./src/movement.js').then(() => console.log('✓ Movement imported'));
    
    console.log('All modules imported successfully');
} catch (e) {
    console.error('Import error:', e);
}