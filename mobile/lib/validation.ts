import { z } from 'zod';
import { isValidPhoneNumber } from 'libphonenumber-js';

// Mirrors backend/app/schemas/auth.py::_validate_password_strength
export const passwordSchema = z
  .string()
  .min(8, 'Password must be at least 8 characters long')
  .regex(/\d/, 'Password must contain at least one digit');

// Mirrors backend/app/schemas/auth.py::_validate_and_normalize_phone. The
// backend validates with Google's libphonenumber (via the `phonenumbers`
// Python port); we use the JS port here so client-side validation agrees
// with the server instead of a hand-rolled regex.
export const phoneSchema = z
  .string()
  .min(1, 'Phone number is required')
  .refine((value) => isValidPhoneNumber(value), {
    message: 'Enter a valid phone number in international format, e.g. +919876543210',
  });

export const emailSchema = z.string().email('Enter a valid email address');

export const registerSchema = z.object({
  full_name: z.string().trim().min(1, 'Full name cannot be empty'),
  email: emailSchema,
  phone_number: phoneSchema,
  password: passwordSchema,
});
export type RegisterFormValues = z.infer<typeof registerSchema>;

export const verifyOtpSchema = z.object({
  phone_number: phoneSchema,
  code: z.string().length(6, 'Enter the 6-digit code'),
});
export type VerifyOtpFormValues = z.infer<typeof verifyOtpSchema>;

export const loginSchema = z.object({
  email: emailSchema,
  password: z.string().min(1, 'Password is required'),
});
export type LoginFormValues = z.infer<typeof loginSchema>;

export const forgotPasswordSchema = z.object({
  email: emailSchema,
});
export type ForgotPasswordFormValues = z.infer<typeof forgotPasswordSchema>;

export const resetPasswordSchema = z.object({
  email: emailSchema,
  code: z.string().length(6, 'Enter the 6-digit code'),
  new_password: passwordSchema,
});
export type ResetPasswordFormValues = z.infer<typeof resetPasswordSchema>;