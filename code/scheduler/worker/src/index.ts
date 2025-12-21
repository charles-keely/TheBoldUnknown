/**
 * TheBoldUnknown Scheduler Worker
 * 
 * Cloudflare Worker that runs as a cron job to:
 * 1. Check for posts due for publishing
 * 2. Ensure the Instagram token is fresh
 * 3. Trigger rendering and publishing
 * 
 * Architecture Note:
 * This worker cannot render HTML to PNG (requires browser/Playwright).
 * It calls the Python API's render endpoint to get public URLs for slides,
 * then handles the Instagram Graph API calls.
 * 
 * For production, consider pre-rendering slides when the schedule is approved.
 */

import type { Env, ScheduledPost, RenderedSlide } from './types';
import {
  getDuePosts,
  markPostPublishing,
  markPostPublished,
  markPostFailed,
  getAssemblyData,
} from './db';
import { ensureFreshToken, validateToken } from './token-manager';
import { publishCarousel, composeCaption } from './publisher';

export default {
  /**
   * Cron trigger handler - runs every minute
   */
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    console.log(`[${new Date().toISOString()}] Scheduler cron triggered`);
    
    try {
      await processScheduledPosts(env);
    } catch (error) {
      console.error('Scheduler error:', error);
    }
  },

  /**
   * HTTP handler for manual triggering and health checks
   */
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    
    // Health check
    if (url.pathname === '/health') {
      return new Response(JSON.stringify({ status: 'ok', timestamp: new Date().toISOString() }), {
        headers: { 'Content-Type': 'application/json' },
      });
    }
    
    // Manual trigger (for testing)
    if (url.pathname === '/trigger' && request.method === 'POST') {
      // Check for a simple auth header (optional security)
      const authHeader = request.headers.get('Authorization');
      if (authHeader !== `Bearer ${env.META_APP_SECRET}`) {
        return new Response('Unauthorized', { status: 401 });
      }
      
      try {
        await processScheduledPosts(env);
        return new Response(JSON.stringify({ status: 'ok', message: 'Processing complete' }), {
          headers: { 'Content-Type': 'application/json' },
        });
      } catch (error) {
        return new Response(JSON.stringify({ status: 'error', message: String(error) }), {
          status: 500,
          headers: { 'Content-Type': 'application/json' },
        });
      }
    }
    
    // Token refresh check
    if (url.pathname === '/token/check') {
      const token = await ensureFreshToken(env);
      if (!token) {
        return new Response(JSON.stringify({ status: 'error', message: 'No token available' }), {
          status: 500,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      
      const valid = await validateToken(env, token);
      return new Response(JSON.stringify({ 
        status: valid ? 'ok' : 'invalid',
        message: valid ? 'Token is valid' : 'Token validation failed',
      }), {
        headers: { 'Content-Type': 'application/json' },
      });
    }
    
    return new Response('TheBoldUnknown Scheduler Worker', { status: 200 });
  },
};

/**
 * Main processing logic
 */
async function processScheduledPosts(env: Env): Promise<void> {
  // 1. Get due posts
  const duePosts = await getDuePosts(env);
  
  if (duePosts.length === 0) {
    console.log('No posts due for publishing');
    return;
  }
  
  console.log(`Found ${duePosts.length} post(s) due for publishing`);
  
  // 2. Ensure we have a fresh token
  const accessToken = await ensureFreshToken(env);
  
  if (!accessToken) {
    console.error('No valid Instagram access token available');
    // Mark all due posts as failed
    const maxRetries = parseInt(env.MAX_RETRY_COUNT || '3', 10);
    for (const post of duePosts) {
      await markPostFailed(env, post.id, 'No valid Instagram access token', post.retry_count, maxRetries);
    }
    return;
  }
  
  // 3. Validate token
  const tokenValid = await validateToken(env, accessToken);
  if (!tokenValid) {
    console.error('Instagram access token validation failed');
    const maxRetries = parseInt(env.MAX_RETRY_COUNT || '3', 10);
    for (const post of duePosts) {
      await markPostFailed(env, post.id, 'Instagram token validation failed', post.retry_count, maxRetries);
    }
    return;
  }
  
  // 4. Process each post
  for (const post of duePosts) {
    await processPost(env, post, accessToken);
  }
}

/**
 * Process a single post
 */
async function processPost(env: Env, post: ScheduledPost, accessToken: string): Promise<void> {
  console.log(`Processing post ${post.id} (story: ${post.story_generation_id})`);
  
  const maxRetries = parseInt(env.MAX_RETRY_COUNT || '3', 10);
  
  // Mark as publishing
  await markPostPublishing(env, post.id);
  
  try {
    // Get assembly data
    const data = await getAssemblyData(env, post.story_generation_id);
    
    if (!data) {
      throw new Error('Assembly data not found');
    }
    
    const { assembly, generation } = data;
    
    // Get rendered slide URLs
    // NOTE: This assumes slides are pre-rendered and URLs are stored in assembly_data
    // If not, we need to call the Python API to render them
    const slides = await getRenderedSlides(env, assembly.assembly_data, post.story_generation_id);
    
    if (slides.length < 2) {
      throw new Error(`Not enough slides for carousel (got ${slides.length}, need at least 2)`);
    }
    
    // Compose caption
    const caption = composeCaption(generation.instagram_caption, generation.hashtags);
    
    // Publish to Instagram
    const result = await publishCarousel(env, accessToken, slides, caption);
    
    if (result.success && result.media_id) {
      await markPostPublished(env, post.id, result.media_id);
      console.log(`Post ${post.id} published successfully! Media ID: ${result.media_id}`);
    } else {
      throw new Error(result.error || 'Unknown publishing error');
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    console.error(`Post ${post.id} failed:`, errorMessage);
    await markPostFailed(env, post.id, errorMessage, post.retry_count, maxRetries);
  }
}

/**
 * Get rendered slide URLs from assembly data
 * 
 * This looks for pre-rendered URLs in the assembly_data.
 * If not found, it will attempt to call the Python render API.
 */
async function getRenderedSlides(
  env: Env,
  assemblyData: any,
  storyGenerationId: string
): Promise<RenderedSlide[]> {
  const slides: RenderedSlide[] = [];
  
  // Check if we have pre-rendered URLs
  if (assemblyData.rendered_slides && Array.isArray(assemblyData.rendered_slides)) {
    for (const slide of assemblyData.rendered_slides) {
      if (slide.public_url) {
        slides.push({
          index: slide.index || slides.length,
          filename: slide.filename || `slide_${slides.length}.png`,
          public_url: slide.public_url,
        });
      }
    }
    
    if (slides.length > 0) {
      console.log(`Found ${slides.length} pre-rendered slides`);
      return slides;
    }
  }
  
  // No pre-rendered slides found
  // In a production setup, you would either:
  // 1. Call a Python API endpoint to render and get URLs
  // 2. Have a separate pre-rendering step that runs before the worker
  
  console.warn('No pre-rendered slides found. Rendering must be done before publishing.');
  console.warn('Ensure slides are rendered and stored when the schedule is approved.');
  
  // For now, try to extract thumbnail/photo URLs from slide content
  // This is a fallback that may not produce optimal results
  const slideData = assemblyData.slides || [];
  let index = 0;
  
  for (const slide of slideData) {
    if (!slide.visible) continue;
    
    let url: string | null = null;
    
    if (slide.type === 'cover' && slide.content?.thumbnail_url) {
      // Convert relative URL to absolute if needed
      url = slide.content.thumbnail_url;
      if (url.startsWith('/api/thumbnails/')) {
        // This is a relative URL to the Python API - can't use directly
        console.warn(`Cover slide has relative thumbnail URL: ${url}`);
        continue;
      }
    } else if (slide.type === 'photo' && slide.content?.image_url) {
      url = slide.content.image_url;
    }
    
    if (url && url.startsWith('http')) {
      slides.push({
        index,
        filename: `slide_${index}.png`,
        public_url: url,
      });
      index++;
    }
  }
  
  console.log(`Extracted ${slides.length} slide URLs from assembly data`);
  
  // If we don't have enough slides, the caller will handle the error
  return slides;
}

