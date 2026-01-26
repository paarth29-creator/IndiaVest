import React from 'react';
import { Stack } from 'expo-router';

export default function TradeLayout() {
  return (
    <Stack
      screenOptions={{
        headerShown: false,
        animation: 'slide_from_right',
      }}
    >
      <Stack.Screen name="index" />
      <Stack.Screen name="daytrading" />
      <Stack.Screen name="highrisk" />
    </Stack>
  );
}
