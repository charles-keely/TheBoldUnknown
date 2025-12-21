/**
 * Instagram Publisher - Handles posting carousels to Instagram
 */

import type { Env, PublishResult, StoryAssembly, StoryGeneration, RenderedSlide } from './types';

/**
 * Create a carousel item container
 */
async function createCarouselItem(
  env: Env,
  accessToken: string,
  imageUrl: string
): Promise<string | null> {
  const url = `https://graph.facebook.com/${env.GRAPH_API_VERSION}/${env.IG_USER_ID}/media`;
  
  const params = new URLSearchParams({
    image_url: imageUrl,
    is_carousel_item: 'true',
    access_token: accessToken,
  });
  
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: params.toString(),
    });
    
    if (!response.ok) {
      const errorText = await response.text();
      console.error('Create carousel item failed:', response.status, errorText);
      return null;
    }
    
    const data = await response.json() as { id?: string };
    return data.id || null;
  } catch (error) {
    console.error('Create carousel item error:', error);
    return null;
  }
}

/**
 * Wait for a media container to be ready
 */
async function waitContainerReady(
  env: Env,
  accessToken: string,
  containerId: string,
  timeoutMs: number = 180000,
  pollIntervalMs: number = 3000
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  
  while (Date.now() < deadline) {
    const url = `https://graph.facebook.com/${env.GRAPH_API_VERSION}/${containerId}?fields=status_code&access_token=${accessToken}`;
    
    try {
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
        },
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('Check container status failed:', response.status, errorText);
        return false;
      }
      
      const data = await response.json() as { status_code?: string };
      const status = data.status_code;
      
      if (status === 'FINISHED') {
        return true;
      }
      
      if (status === 'ERROR' || status === 'EXPIRED') {
        console.error(`Container ${containerId} has status: ${status}`);
        return false;
      }
      
      // Wait before polling again
      await new Promise(resolve => setTimeout(resolve, pollIntervalMs));
    } catch (error) {
      console.error('Check container status error:', error);
      return false;
    }
  }
  
  console.error(`Timeout waiting for container ${containerId}`);
  return false;
}

/**
 * Create a carousel container
 */
async function createCarouselContainer(
  env: Env,
  accessToken: string,
  childrenIds: string[],
  caption: string
): Promise<string | null> {
  const url = `https://graph.facebook.com/${env.GRAPH_API_VERSION}/${env.IG_USER_ID}/media`;
  
  const params = new URLSearchParams({
    media_type: 'CAROUSEL',
    children: childrenIds.join(','),
    caption: caption,
    access_token: accessToken,
  });
  
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: params.toString(),
    });
    
    if (!response.ok) {
      const errorText = await response.text();
      console.error('Create carousel container failed:', response.status, errorText);
      return null;
    }
    
    const data = await response.json() as { id?: string };
    return data.id || null;
  } catch (error) {
    console.error('Create carousel container error:', error);
    return null;
  }
}

/**
 * Publish a media container
 */
async function publishMedia(
  env: Env,
  accessToken: string,
  creationId: string
): Promise<string | null> {
  const url = `https://graph.facebook.com/${env.GRAPH_API_VERSION}/${env.IG_USER_ID}/media_publish`;
  
  const params = new URLSearchParams({
    creation_id: creationId,
    access_token: accessToken,
  });
  
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: params.toString(),
    });
    
    if (!response.ok) {
      const errorText = await response.text();
      console.error('Publish media failed:', response.status, errorText);
      return null;
    }
    
    const data = await response.json() as { id?: string };
    return data.id || null;
  } catch (error) {
    console.error('Publish media error:', error);
    return null;
  }
}

/**
 * Compose the caption from story data
 */
export function composeCaption(
  caption: string | null,
  hashtags: string[] | null
): string {
  let result = (caption || '').trim();
  
  if (hashtags && hashtags.length > 0) {
    const tagsText = hashtags
      .map(tag => tag.startsWith('#') ? tag : `#${tag}`)
      .join(' ');
    
    if (result) {
      result = `${result}\n\n${tagsText}`;
    } else {
      result = tagsText;
    }
  }
  
  return result;
}

/**
 * Publish a carousel post to Instagram
 * 
 * Note: This expects pre-rendered slides with public URLs.
 * The Python API handles rendering; the worker just publishes.
 */
export async function publishCarousel(
  env: Env,
  accessToken: string,
  slides: RenderedSlide[],
  caption: string
): Promise<PublishResult> {
  // Instagram requires 2-10 items for a carousel
  if (slides.length < 2) {
    return {
      success: false,
      error: 'Carousel requires at least 2 slides',
    };
  }
  
  if (slides.length > 10) {
    console.log(`Truncating ${slides.length} slides to 10`);
    slides = slides.slice(0, 10);
  }
  
  // Step 1: Create carousel items
  console.log(`Creating ${slides.length} carousel items...`);
  const childrenIds: string[] = [];
  
  for (const slide of slides) {
    const itemId = await createCarouselItem(env, accessToken, slide.public_url);
    
    if (!itemId) {
      return {
        success: false,
        error: `Failed to create carousel item for slide ${slide.index}`,
      };
    }
    
    // Wait for item to be ready
    const ready = await waitContainerReady(env, accessToken, itemId);
    if (!ready) {
      return {
        success: false,
        error: `Carousel item ${slide.index} failed to become ready`,
      };
    }
    
    childrenIds.push(itemId);
    console.log(`Carousel item ${slide.index} ready: ${itemId}`);
  }
  
  // Step 2: Create carousel container
  console.log('Creating carousel container...');
  const carouselId = await createCarouselContainer(env, accessToken, childrenIds, caption);
  
  if (!carouselId) {
    return {
      success: false,
      error: 'Failed to create carousel container',
    };
  }
  
  // Wait for carousel to be ready
  const carouselReady = await waitContainerReady(env, accessToken, carouselId);
  if (!carouselReady) {
    return {
      success: false,
      error: 'Carousel container failed to become ready',
    };
  }
  
  console.log(`Carousel container ready: ${carouselId}`);
  
  // Step 3: Publish
  console.log('Publishing carousel...');
  const mediaId = await publishMedia(env, accessToken, carouselId);
  
  if (!mediaId) {
    return {
      success: false,
      error: 'Failed to publish carousel',
    };
  }
  
  console.log(`Successfully published! Media ID: ${mediaId}`);
  
  return {
    success: true,
    media_id: mediaId,
  };
}

