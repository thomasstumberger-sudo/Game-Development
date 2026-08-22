/** 
 * Resource feedback system - tracks recent resource changes for visual feedback
 * 
 * Pure module: no DOM, no side effects on import.
 */
export let RESOURCE_FEEDBACK = {
    changes: [],
    maxAge: 1500, // 1.5 seconds
    
    addChange(resource, amount) {
        this.changes.push({
            resource,
            amount,
            time: Date.now()
        });
    },
    
    getChanges() {
        const now = Date.now();
        return this.changes.filter(change => now - change.time < this.maxAge);
    },
    
    clearOld() {
        const now = Date.now();
        this.changes = this.changes.filter(change => now - change.time < this.maxAge);
    }
};