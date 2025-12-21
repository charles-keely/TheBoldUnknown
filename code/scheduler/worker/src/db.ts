/**
 * Database operations using Supabase
 */

import { createClient, SupabaseClient } from '@supabase/supabase-js';
import type { Env, ScheduledPost, IGAccessToken, StoryAssembly, StoryGeneration } from './types';

let supabaseClient: SupabaseClient | null = null;

export function getSupabase(env: Env): SupabaseClient {
  if (!supabaseClient) {
    supabaseClient = createClient(env.SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY, {
      auth: {
        persistSession: false,
        autoRefreshToken: false,
      },
    });
  }
  return supabaseClient;
}

/**
 * Get posts that are due for publishing
 */
export async function getDuePosts(env: Env): Promise<ScheduledPost[]> {
  const supabase = getSupabase(env);
  const now = new Date().toISOString();
  
  const { data, error } = await supabase
    .from('scheduled_posts')
    .select('*')
    .eq('status', 'approved')
    .lte('scheduled_at', now)
    .order('scheduled_at', { ascending: true })
    .limit(10);  // Process up to 10 posts per cron run
  
  if (error) {
    console.error('Error fetching due posts:', error);
    return [];
  }
  
  return data || [];
}

/**
 * Update post status to 'publishing'
 */
export async function markPostPublishing(env: Env, postId: string): Promise<boolean> {
  const supabase = getSupabase(env);
  
  const { error } = await supabase
    .from('scheduled_posts')
    .update({
      status: 'publishing',
      updated_at: new Date().toISOString(),
    })
    .eq('id', postId);
  
  if (error) {
    console.error('Error marking post as publishing:', error);
    return false;
  }
  
  return true;
}

/**
 * Mark post as successfully published
 */
export async function markPostPublished(
  env: Env,
  postId: string,
  instagramMediaId: string
): Promise<boolean> {
  const supabase = getSupabase(env);
  
  const { error } = await supabase
    .from('scheduled_posts')
    .update({
      status: 'published',
      published_at: new Date().toISOString(),
      instagram_media_id: instagramMediaId,
      error_message: null,
      updated_at: new Date().toISOString(),
    })
    .eq('id', postId);
  
  if (error) {
    console.error('Error marking post as published:', error);
    return false;
  }
  
  return true;
}

/**
 * Mark post as failed
 */
export async function markPostFailed(
  env: Env,
  postId: string,
  errorMessage: string,
  currentRetryCount: number,
  maxRetries: number
): Promise<boolean> {
  const supabase = getSupabase(env);
  const newRetryCount = currentRetryCount + 1;
  
  if (newRetryCount < maxRetries) {
    // Reschedule for 5 minutes later
    const newScheduledAt = new Date(Date.now() + 5 * 60 * 1000).toISOString();
    
    const { error } = await supabase
      .from('scheduled_posts')
      .update({
        status: 'approved',  // Back to approved for retry
        scheduled_at: newScheduledAt,
        error_message: errorMessage,
        retry_count: newRetryCount,
        updated_at: new Date().toISOString(),
      })
      .eq('id', postId);
    
    if (error) {
      console.error('Error rescheduling failed post:', error);
      return false;
    }
    
    console.log(`Post ${postId} rescheduled for retry ${newRetryCount}/${maxRetries}`);
  } else {
    // Max retries reached, mark as permanently failed
    const { error } = await supabase
      .from('scheduled_posts')
      .update({
        status: 'failed',
        error_message: errorMessage,
        retry_count: newRetryCount,
        updated_at: new Date().toISOString(),
      })
      .eq('id', postId);
    
    if (error) {
      console.error('Error marking post as failed:', error);
      return false;
    }
    
    console.log(`Post ${postId} marked as failed after ${maxRetries} retries`);
  }
  
  return true;
}

/**
 * Get the active Instagram access token
 */
export async function getActiveToken(env: Env): Promise<IGAccessToken | null> {
  const supabase = getSupabase(env);
  
  const { data, error } = await supabase
    .from('ig_access_tokens')
    .select('*')
    .eq('is_active', true)
    .order('created_at', { ascending: false })
    .limit(1)
    .single();
  
  if (error) {
    console.error('Error fetching active token:', error);
    return null;
  }
  
  return data;
}

/**
 * Save a new token and deactivate old ones
 */
export async function saveNewToken(
  env: Env,
  accessToken: string,
  expiresAt: string,
  tokenType: string = 'bearer'
): Promise<boolean> {
  const supabase = getSupabase(env);
  
  // Deactivate all existing tokens
  await supabase
    .from('ig_access_tokens')
    .update({
      is_active: false,
      updated_at: new Date().toISOString(),
    })
    .eq('is_active', true);
  
  // Insert new token
  const { error } = await supabase
    .from('ig_access_tokens')
    .insert({
      access_token: accessToken,
      token_type: tokenType,
      expires_at: expiresAt,
      is_active: true,
      obtained_at: new Date().toISOString(),
    });
  
  if (error) {
    console.error('Error saving new token:', error);
    return false;
  }
  
  return true;
}

/**
 * Update token's last_used_at timestamp
 */
export async function updateTokenLastUsed(env: Env, tokenId: string): Promise<void> {
  const supabase = getSupabase(env);
  
  await supabase
    .from('ig_access_tokens')
    .update({
      last_used_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    })
    .eq('id', tokenId);
}

/**
 * Get assembly data for a post
 */
export async function getAssemblyData(
  env: Env,
  storyGenerationId: string
): Promise<{ assembly: StoryAssembly; generation: StoryGeneration } | null> {
  const supabase = getSupabase(env);
  
  // Get the assembly
  const { data: assembly, error: assemblyError } = await supabase
    .from('story_assemblies')
    .select('*')
    .eq('story_generation_id', storyGenerationId)
    .order('updated_at', { ascending: false })
    .limit(1)
    .single();
  
  if (assemblyError || !assembly) {
    console.error('Error fetching assembly:', assemblyError);
    return null;
  }
  
  // Get the story generation for caption/hashtags
  const { data: generation, error: generationError } = await supabase
    .from('story_generations')
    .select('id, hook_title, subtitle, domain_tag, instagram_caption, hashtags')
    .eq('id', storyGenerationId)
    .single();
  
  if (generationError || !generation) {
    console.error('Error fetching story generation:', generationError);
    return null;
  }
  
  return { assembly, generation };
}

/**
 * Get public URL for a rendered slide from Supabase Storage
 */
export async function getStoragePublicUrl(
  env: Env,
  bucket: string,
  path: string
): Promise<string> {
  const supabase = getSupabase(env);
  const { data } = supabase.storage.from(bucket).getPublicUrl(path);
  return data.publicUrl;
}

/**
 * Upload rendered slide to Supabase Storage
 */
export async function uploadToStorage(
  env: Env,
  bucket: string,
  path: string,
  data: ArrayBuffer,
  contentType: string
): Promise<string | null> {
  const supabase = getSupabase(env);
  
  const { error } = await supabase.storage
    .from(bucket)
    .upload(path, data, {
      contentType,
      upsert: true,
    });
  
  if (error) {
    console.error('Error uploading to storage:', error);
    return null;
  }
  
  return getStoragePublicUrl(env, bucket, path);
}

