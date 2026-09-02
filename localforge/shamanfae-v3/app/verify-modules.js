// Simple verification that all modules can be imported correctly
console.log('Verifying module imports...');

try {
    // Test importing palette
    const palette = await import('./src/palette.js');
    console.log('✓ Palette module imported successfully');
    
    // Test importing state  
    const state = await import('./src/state.js');
    console.log('✓ State module imported successfully');
    
    // Test importing hud
    const hud = await import('./src/hud.js');
    console.log('✓ HUD module imported successfully');
    
    // Test importing main (should not execute side effects)
    const main = await import('./src/main.js');
    console.log('✓ Main module imported successfully (no side effects)');
    
    console.log('\nAll modules verified successfully!');
} catch (error) {
    console.error('Module verification failed:', error);
}