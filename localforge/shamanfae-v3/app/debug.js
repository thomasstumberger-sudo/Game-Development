// Simple debug script to test if modules are working correctly
console.log("Debug: Starting module tests");

// Test importing modules
try {
    import('./src/palette.js').then(() => console.log("Palette imported successfully"));
} catch (e) {
    console.error("Failed to import palette:", e);
}

try {
    import('./src/hex.js').then(() => console.log("Hex imported successfully"));
} catch (e) {
    console.error("Failed to import hex:", e);
}

try {
    import('./src/state.js').then(() => console.log("State imported successfully"));
} catch (e) {
    console.error("Failed to import state:", e);
}

console.log("Debug: Module tests completed");