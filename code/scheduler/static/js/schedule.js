/**
 * Scheduler Alpine.js Component
 */

function scheduler() {
  return {
    // Data
    posts: [],
    loading: true,
    error: null,
    syncing: false,
    approving: false,
    
    // Counts
    pendingCount: 0,
    approvedCount: 0,
    publishedCount: 0,
    failedCount: 0,
    
    // Token status
    tokenStatus: {
      has_token: false,
      is_healthy: false,
      days_until_expiry: null,
    },
    
    // UI State
    editingTimeId: null,
    showApproveModal: false,
    deleteModal: {
      show: false,
      post: null,
    },
    
    // Sortable instance
    sortable: null,
    
    // =========================================================================
    // Initialization
    // =========================================================================
    
    async init() {
      await this.loadSchedule();
      await this.loadTokenStatus();
      this.initSortable();
    },
    
    initSortable() {
      this.$nextTick(() => {
        const el = this.$refs.scheduleList;
        if (!el) return;
        
        this.sortable = new Sortable(el, {
          handle: '.drag-handle',
          animation: 200,
          ghostClass: 'sortable-ghost',
          chosenClass: 'sortable-chosen',
          filter: '.opacity-60', // Don't allow dragging published posts
          onEnd: async (evt) => {
            if (evt.oldIndex === evt.newIndex) return;
            
            const postId = evt.item.dataset.id;
            const newPosition = evt.newIndex;
            
            try {
              const response = await fetch(`api/schedule/${postId}/move`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_position: newPosition }),
              });
              
              if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
              }
              
              const data = await response.json();
              this.posts = data.schedule;
            } catch (err) {
              console.error('Failed to reorder:', err);
              this.error = 'Failed to reorder posts';
              // Reload to reset order
              await this.loadSchedule();
            }
          },
        });
      });
    },
    
    // =========================================================================
    // API Calls
    // =========================================================================
    
    async loadSchedule() {
      this.loading = true;
      this.error = null;
      
      try {
        const response = await fetch('api/schedule');
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        this.posts = data.posts || [];
        this.pendingCount = data.pending_count || 0;
        this.approvedCount = data.approved_count || 0;
        this.publishedCount = data.published_count || 0;
        this.failedCount = data.failed_count || 0;
      } catch (err) {
        console.error('Failed to load schedule:', err);
        this.error = err.message;
      } finally {
        this.loading = false;
      }
    },
    
    async loadTokenStatus() {
      try {
        const response = await fetch('api/tokens/status');
        if (response.ok) {
          this.tokenStatus = await response.json();
        }
      } catch (err) {
        console.error('Failed to load token status:', err);
      }
    },
    
    async syncSchedule() {
      this.syncing = true;
      this.error = null;
      
      try {
        const response = await fetch('api/schedule/sync', {
          method: 'POST',
        });
        
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        this.posts = data.schedule || [];
        
        // Reload counts
        await this.loadSchedule();
        
        if (data.added > 0) {
          console.log(`Added ${data.added} new posts to schedule`);
        }
      } catch (err) {
        console.error('Failed to sync schedule:', err);
        this.error = err.message;
      } finally {
        this.syncing = false;
      }
    },
    
    async approveSchedule() {
      this.approving = true;
      
      try {
        const response = await fetch('api/schedule/approve', {
          method: 'POST',
        });
        
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        console.log(`Approved ${data.approved_count} posts`);
        
        this.showApproveModal = false;
        await this.loadSchedule();
      } catch (err) {
        console.error('Failed to approve schedule:', err);
        this.error = err.message;
      } finally {
        this.approving = false;
      }
    },
    
    async updatePostTime(postId, dateTimeValue) {
      if (!dateTimeValue) return;
      
      try {
        // Convert local datetime to ISO string
        const scheduledAt = new Date(dateTimeValue).toISOString();
        
        const response = await fetch(`api/schedule/${postId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ scheduled_at: scheduledAt }),
        });
        
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        
        const updated = await response.json();
        
        // Update local state
        const index = this.posts.findIndex(p => p.id === postId);
        if (index !== -1) {
          this.posts[index] = updated;
        }
        
        this.editingTimeId = null;
      } catch (err) {
        console.error('Failed to update time:', err);
        this.error = 'Failed to update time';
      }
    },
    
    async retryPost(postId) {
      try {
        const response = await fetch(`api/schedule/${postId}/retry`, {
          method: 'POST',
        });
        
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        
        await this.loadSchedule();
      } catch (err) {
        console.error('Failed to retry post:', err);
        this.error = err.message;
      }
    },
    
    confirmDelete(post) {
      this.deleteModal.post = post;
      this.deleteModal.show = true;
    },
    
    async deletePost() {
      if (!this.deleteModal.post) return;
      
      const postId = this.deleteModal.post.id;
      
      try {
        const response = await fetch(`api/schedule/${postId}`, {
          method: 'DELETE',
        });
        
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        
        this.deleteModal.show = false;
        this.deleteModal.post = null;
        
        await this.loadSchedule();
      } catch (err) {
        console.error('Failed to delete post:', err);
        this.error = err.message;
      }
    },
    
    // =========================================================================
    // UI Helpers
    // =========================================================================
    
    toggleTimeEdit(postId) {
      this.editingTimeId = this.editingTimeId === postId ? null : postId;
    },
    
    formatTime(isoString) {
      if (!isoString) return '';
      const date = new Date(isoString);
      return date.toLocaleTimeString('en-US', {
        hour: 'numeric',
        minute: '2-digit',
        hour12: true,
        timeZone: 'America/Denver',
      });
    },
    
    formatDate(isoString) {
      if (!isoString) return '';
      const date = new Date(isoString);
      const today = new Date();
      const tomorrow = new Date(today);
      tomorrow.setDate(tomorrow.getDate() + 1);
      
      // Check if today
      if (date.toDateString() === today.toDateString()) {
        return 'Today';
      }
      
      // Check if tomorrow
      if (date.toDateString() === tomorrow.toDateString()) {
        return 'Tomorrow';
      }
      
      return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        timeZone: 'America/Denver',
      });
    },
    
    formatDateTimeLocal(isoString) {
      if (!isoString) return '';
      const date = new Date(isoString);
      // Adjust for MST timezone
      const offset = date.getTimezoneOffset();
      const mstOffset = 7 * 60; // MST is UTC-7
      const adjusted = new Date(date.getTime() - (mstOffset - offset) * 60000);
      return adjusted.toISOString().slice(0, 16);
    },
  };
}

