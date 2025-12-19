/**
 * Template Wrapper Script
 * 
 * This script is injected into template iframes to enable communication
 * with the parent editor via postMessage.
 * 
 * Features:
 * - Receives content updates from parent
 * - Updates page numbers dynamically
 * - Handles contenteditable mode for inline editing
 * - Reports content changes back to parent
 */

(function() {
  'use strict';
  
  // Slide ID set by parent when loading the iframe
  window.__slideId = window.__slideId || null;
  window.__slideType = window.__slideType || null;
  
  // Listen for messages from parent (editor)
  window.addEventListener('message', function(event) {
    // In production, validate event.origin
    const { type, payload } = event.data || {};
    
    if (!type) return;
    
    switch(type) {
      case 'INIT':
        // Initialize slide metadata
        window.__slideId = payload.slideId;
        window.__slideType = payload.slideType;
        if (payload.content) {
          updateContent(payload.content);
        }
        if (payload.pageNumber) {
          updatePageNumber(payload.pageNumber.current, payload.pageNumber.total);
        }
        break;
        
      case 'UPDATE_PAGE_NUMBER':
        updatePageNumber(payload.current, payload.total);
        break;
        
      case 'UPDATE_CONTENT':
        updateContent(payload);
        break;
        
      case 'SET_EDITABLE':
        setContentEditable(payload.editable);
        break;
        
      case 'GET_CONTENT':
        // Parent is requesting current content
        sendCurrentContent();
        break;
    }
  });
  
  /**
   * Update page number display
   * Handles both cover format (01/08 + SWIPE) and editorial format (01 / 08)
   */
  function updatePageNumber(current, total) {
    // Closing template format: show FINAL // NN (uses total)
    const footerFinal = document.querySelector('.footer-final') || document.querySelector('.footer-right');
    if (footerFinal && footerFinal.classList && footerFinal.classList.contains('footer-final')) {
      const formattedTotal = `${String(total).padStart(2, '0')}`;
      footerFinal.textContent = `FINAL // ${formattedTotal}`;
      return;
    }
    // Back-compat: older closing template used .footer-right for FINAL.
    // Guard with a closing-specific element so we don't affect unrelated templates.
    if (footerFinal && !document.querySelector('.page-number') && document.querySelector('.sources-container')) {
      const formattedTotal = `${String(total).padStart(2, '0')}`;
      footerFinal.textContent = `FINAL // ${formattedTotal}`;
      return;
    }

    // Editorial/Photo template format
    const pageNumber = document.querySelector('.page-number');
    if (pageNumber) {
      const formatted = `${String(current).padStart(2, '0')} / ${String(total).padStart(2, '0')}`;
      pageNumber.textContent = formatted;
      return;
    }

    // Cover template format (detect by swipe arrow / cover footer structure)
    const footerLeft = document.querySelector('.footer-left');
    const hasCoverArrow = !!(document.querySelector('.arrow-container') || document.querySelector('.swipe-arrow'));
    if (footerLeft && hasCoverArrow) {
      const formatted = `${String(current).padStart(2, '0')}/${String(total).padStart(2, '0')}`;
      footerLeft.innerHTML = `${formatted}<br>SWIPE FOR MORE`;
      return;
    }
  }
  
  /**
   * Update template content based on slide type
   */
  function updateContent(content) {
    if (!content) return;

    // Back-compat / aliasing (older assembly shapes)
    const normalized = { ...content };
    if (normalized.text === undefined && normalized.text_content !== undefined) {
      normalized.text = normalized.text_content;
    }
    if (normalized.image_url === undefined && normalized.imageUrl !== undefined) {
      normalized.image_url = normalized.imageUrl;
    }
    if (normalized.thumbnail_url === undefined && normalized.thumbnailUrl !== undefined) {
      normalized.thumbnail_url = normalized.thumbnailUrl;
    }
    if (normalized.title === undefined && normalized.hook_title !== undefined) {
      normalized.title = normalized.hook_title;
    }
    if (normalized.source === undefined && normalized.source_attribution !== undefined) {
      normalized.source = normalized.source_attribution;
    }
    if (normalized.domain_tag === undefined && normalized.domainTag !== undefined) {
      normalized.domain_tag = normalized.domainTag;
    }
    
    // === COVER TEMPLATE ===
    if (normalized.title !== undefined) {
      const title = document.querySelector('.main-title');
      if (title) {
        // Replace newlines with <br> for multi-line titles
        title.innerHTML = String(normalized.title).replace(/\n/g, '<br>');
      }
    }
    
    if (normalized.subtitle !== undefined) {
      const subtitle = document.querySelector('.subtitle');
      if (subtitle) {
        subtitle.textContent = String(normalized.subtitle);
      }
    }
    
    if (normalized.thumbnail_url) {
      const bg = document.querySelector('.bg-image');
      if (bg) {
        bg.src = normalized.thumbnail_url;
      }
    }

    // Non-destructive cover "crop" controls: zoom + x/y pan for bg-image
    // Applied via CSS transform so user can always zoom back out.
    {
      const bg = document.querySelector('.bg-image');
      if (bg) {
        const zoomRaw = normalized.thumbnail_zoom;
        const xRaw = normalized.thumbnail_offset_x;
        const yRaw = normalized.thumbnail_offset_y;

        const zoom = clampNumber(zoomRaw, 1, 4, 1);
        const x = clampNumber(xRaw, -2000, 2000, 0);
        const y = clampNumber(yRaw, -2000, 2000, 0);

        bg.style.transformOrigin = 'center center';
        // NOTE: transform functions are applied right-to-left; this ordering
        // keeps translate values from being scaled.
        bg.style.transform = `translate(${x}px, ${y}px) scale(${zoom})`;
        bg.style.willChange = 'transform';
      }
    }
    
    // === EDITORIAL TEMPLATE ===
    if (normalized.text !== undefined) {
      const col = document.querySelector('.text-column');
      if (col) {
        // Split into paragraphs by double newlines
        const paragraphs = String(normalized.text).split(/\n\n+/).filter(p => p.trim());
        if (paragraphs.length > 0) {
          col.innerHTML = paragraphs.map(p => `<p>${escapeHtml(p)}</p>`).join('');
        } else {
          col.innerHTML = '';
        }
      }
    }
    
    // === PHOTO TEMPLATE ===
    if (normalized.image_url) {
      const img = document.querySelector('.display-photo') || document.querySelector('#main-photo');
      if (img) {
        img.src = normalized.image_url;
      }
    }
    
    if (normalized.caption !== undefined) {
      const cap = document.querySelector('.caption-text') || document.querySelector('#caption-text');
      if (cap) {
        cap.textContent = String(normalized.caption || '');
      }
    }
    
    if (normalized.source !== undefined) {
      const src = document.querySelector('.source-text') || document.querySelector('#source-text');
      if (src) {
        src.textContent = String(normalized.source || '');
      }
    }

    // === CLOSING TEMPLATE: Primary Sources ===
    {
      const container = document.querySelector('.sources-container');
      const list = container ? (container.querySelector('.sources-list') || container) : null;
      if (container && list) {
        const namesRaw = normalized.primary_sources;
        const urlsRaw = normalized.primary_source_urls;
        const names = Array.isArray(namesRaw) ? namesRaw : [];
        const urls = Array.isArray(urlsRaw) ? urlsRaw : [];

        const n = Math.max(names.length, urls.length);
        const items = [];
        for (let i = 0; i < n; i++) {
          const name = (names[i] != null) ? String(names[i]).trim() : '';
          const url = (urls[i] != null) ? String(urls[i]).trim() : '';
          if (!name && !url) continue;
          items.push({ name, url });
        }

        if (items.length === 0) {
          container.style.display = 'none';
        } else {
          container.style.display = '';
          // Clear existing placeholder items
          while (list.firstChild) list.removeChild(list.firstChild);

          items.forEach(({ name, url }) => {
            const span = document.createElement('span');
            span.className = 'source-item';

            const label = name || url;
            if (url) {
              const a = document.createElement('a');
              a.href = url;
              a.textContent = label;
              a.target = '_blank';
              a.rel = 'noopener noreferrer';
              a.style.color = 'inherit';
              a.style.textDecoration = 'none';
              span.appendChild(a);
            } else {
              span.textContent = label;
            }

            list.appendChild(span);
          });
        }
      }
    }
    
    // === COMMON: Domain tag in meta-data ===
    if (normalized.domain_tag !== undefined) {
      const meta = document.querySelector('.meta-data');
      if (meta && String(meta.getAttribute('data-static') || '').toLowerCase() !== 'true') {
        // If the template provides a dedicated domain line, only update that
        // (so templates like the closing slide can keep an "END OF FILE" subline).
        const domainLine = meta.querySelector('.domain-tag-line');
        if (domainLine) {
          domainLine.textContent = String(normalized.domain_tag || '').toUpperCase();
        } else {
          // Default behavior for existing templates
          meta.innerHTML = String(normalized.domain_tag).toUpperCase();
        }
      }
    }

    // === CLOSING TEMPLATE: Auto-update year in footer ===
    {
      // Guard with closing-specific elements so we don't touch other templates.
      const isClosing = !!document.querySelector('.sources-container');
      const yearEl = document.querySelector('.brand-year');
      if (isClosing && yearEl) {
        yearEl.textContent = String(new Date().getFullYear());
      }
    }
  }
  
  /**
   * Enable/disable content editing mode
   */
  function setContentEditable(editable) {
    const editableSelectors = [
      '.main-title',
      '.subtitle',
      '.text-column',
      '.text-column p',
      '.caption-text'
    ];
    
    editableSelectors.forEach(sel => {
      const elements = document.querySelectorAll(sel);
      elements.forEach(el => {
        el.contentEditable = editable ? 'true' : 'false';
        
        if (editable) {
          el.style.outline = '2px dashed rgba(0, 122, 255, 0.5)';
          el.style.outlineOffset = '4px';
          el.addEventListener('blur', handleContentChange);
          el.addEventListener('input', handleContentInput);
        } else {
          el.style.outline = 'none';
          el.style.outlineOffset = '0';
          el.removeEventListener('blur', handleContentChange);
          el.removeEventListener('input', handleContentInput);
        }
      });
    });
    
    // Notify parent that edit mode changed
    window.parent.postMessage({
      type: 'EDIT_MODE_CHANGED',
      slideId: window.__slideId,
      editable: editable
    }, '*');
  }
  
  /**
   * Handle content input (for real-time updates)
   */
  function handleContentInput(event) {
    // Debounce or throttle in production
  }
  
  /**
   * Handle content change (on blur)
   */
  function handleContentChange(event) {
    sendCurrentContent();
  }
  
  /**
   * Send current content to parent
   */
  function sendCurrentContent() {
    const content = {};
    
    // Cover content
    const title = document.querySelector('.main-title');
    if (title) {
      content.title = title.textContent;
    }
    
    const subtitle = document.querySelector('.subtitle');
    if (subtitle) {
      content.subtitle = subtitle.textContent;
    }
    
    // Editorial content
    const textCol = document.querySelector('.text-column');
    if (textCol) {
      // Collect text from all paragraphs
      const paragraphs = textCol.querySelectorAll('p');
      if (paragraphs.length > 0) {
        content.text = Array.from(paragraphs).map(p => p.textContent).join('\n\n');
      } else {
        content.text = textCol.textContent;
      }
    }
    
    // Photo content
    const caption = document.querySelector('.caption-text') || document.querySelector('#caption-text');
    if (caption) {
      content.caption = caption.textContent;
    }
    
    window.parent.postMessage({
      type: 'CONTENT_CHANGED',
      slideId: window.__slideId,
      content: content
    }, '*');
  }
  
  /**
   * Escape HTML to prevent XSS
   */
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function clampNumber(value, min, max, fallback) {
    const n = Number(value);
    if (!Number.isFinite(n)) return fallback;
    return Math.max(min, Math.min(max, n));
  }
  
  /**
   * Signal to parent that template is ready
   */
  function signalReady() {
    window.parent.postMessage({
      type: 'TEMPLATE_READY',
      slideId: window.__slideId
    }, '*');
  }
  
  // Signal ready when DOM is loaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', signalReady);
  } else {
    signalReady();
  }
  
  // Also signal ready after window load (for images/fonts)
  window.addEventListener('load', function() {
    window.parent.postMessage({
      type: 'TEMPLATE_LOADED',
      slideId: window.__slideId
    }, '*');
  });
  
})();

