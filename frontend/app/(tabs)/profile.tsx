import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
  Alert,
  Modal,
  Image,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../src/context/AuthContext';
import { api } from '../../src/services/api';

interface WatchlistItem {
  item_id: string;
  asset_type: string;
  asset_symbol: string;
  asset_name: string;
  current_price: number;
  change_24h: number;
  ai_score: number;
}

interface EducationTip {
  id: string;
  title: string;
  content: string;
  category: string;
}

export default function ProfileScreen() {
  const { user, logout } = useAuth();
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [tips, setTips] = useState<EducationTip[]>([]);
  const [loading, setLoading] = useState(true);
  const [addWatchlistModal, setAddWatchlistModal] = useState(false);
  const [tipModal, setTipModal] = useState<EducationTip | null>(null);
  const [newAsset, setNewAsset] = useState({ type: 'crypto', symbol: '', name: '' });
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [watchlistRes, tipsRes]: any[] = await Promise.all([
        api.getWatchlist(),
        api.getEducationTips(),
      ]);
      setWatchlist(watchlistRes.watchlist || []);
      setTips(tipsRes.tips || []);
    } catch (error) {
      console.error('Error fetching data:', error);
    } finally {
      setLoading(false);
    }
  };

  const addToWatchlist = async () => {
    if (!newAsset.symbol || !newAsset.name) {
      Alert.alert('Error', 'Please fill all fields');
      return;
    }

    try {
      setSubmitting(true);
      await api.addToWatchlist({
        asset_type: newAsset.type,
        asset_symbol: newAsset.symbol.toUpperCase(),
        asset_name: newAsset.name,
      });
      setAddWatchlistModal(false);
      setNewAsset({ type: 'crypto', symbol: '', name: '' });
      fetchData();
    } catch (error: any) {
      Alert.alert('Error', error.message || 'Failed to add to watchlist');
    } finally {
      setSubmitting(false);
    }
  };

  const removeFromWatchlist = async (itemId: string) => {
    Alert.alert(
      'Remove from Watchlist',
      'Are you sure you want to remove this item?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Remove',
          style: 'destructive',
          onPress: async () => {
            try {
              await api.removeFromWatchlist(itemId);
              fetchData();
            } catch (error) {
              Alert.alert('Error', 'Failed to remove item');
            }
          },
        },
      ]
    );
  };

  const handleLogout = () => {
    Alert.alert(
      'Logout',
      'Are you sure you want to logout?',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Logout', style: 'destructive', onPress: logout },
      ]
    );
  };

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0,
    }).format(value);
  };

  const renderWatchlistItem = (item: WatchlistItem) => (
    <View key={item.item_id} style={styles.watchlistCard}>
      <View style={styles.watchlistInfo}>
        <View style={styles.watchlistHeader}>
          <Ionicons 
            name={item.asset_type === 'crypto' ? 'logo-bitcoin' : 'business'} 
            size={24} 
            color={item.asset_type === 'crypto' ? '#f7931a' : '#3b82f6'} 
          />
          <View style={styles.watchlistNameContainer}>
            <Text style={styles.watchlistSymbol}>{item.asset_symbol}</Text>
            <Text style={styles.watchlistName} numberOfLines={1}>{item.asset_name}</Text>
          </View>
        </View>
        <View style={styles.watchlistPriceContainer}>
          <Text style={styles.watchlistPrice}>{formatCurrency(item.current_price)}</Text>
          <Text style={[
            styles.watchlistChange,
            { color: item.change_24h >= 0 ? '#10b981' : '#ef4444' }
          ]}>
            {item.change_24h >= 0 ? '+' : ''}{item.change_24h.toFixed(2)}%
          </Text>
        </View>
      </View>
      <View style={styles.watchlistFooter}>
        <View style={styles.aiScoreBadge}>
          <Ionicons name="sparkles" size={12} color="#6366f1" />
          <Text style={styles.aiScoreText}>AI Score: {item.ai_score}</Text>
        </View>
        <TouchableOpacity onPress={() => removeFromWatchlist(item.item_id)}>
          <Ionicons name="trash-outline" size={20} color="#ef4444" />
        </TouchableOpacity>
      </View>
    </View>
  );

  const getTipIcon = (category: string) => {
    switch (category) {
      case 'tax': return 'receipt-outline';
      case 'disclaimer': return 'alert-circle-outline';
      case 'strategy': return 'bulb-outline';
      default: return 'information-circle-outline';
    }
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color="#6366f1" />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView style={styles.scrollView} contentContainerStyle={styles.content}>
        {/* Profile Header */}
        <View style={styles.profileCard}>
          <View style={styles.profileHeader}>
            {user?.picture ? (
              <Image source={{ uri: user.picture }} style={styles.avatar} />
            ) : (
              <View style={styles.avatarPlaceholder}>
                <Ionicons name="person" size={32} color="#6366f1" />
              </View>
            )}
            <View style={styles.profileInfo}>
              <Text style={styles.profileName}>{user?.name}</Text>
              <Text style={styles.profileEmail}>{user?.email}</Text>
            </View>
          </View>
          <View style={styles.profileStats}>
            <View style={styles.profileStatItem}>
              <Text style={styles.profileStatValue}>
                {formatCurrency(user?.capital || 100000)}
              </Text>
              <Text style={styles.profileStatLabel}>Virtual Capital</Text>
            </View>
            <View style={styles.profileStatDivider} />
            <View style={styles.profileStatItem}>
              <Text style={styles.profileStatValue}>
                {user?.risk_profile?.charAt(0).toUpperCase() + (user?.risk_profile?.slice(1) || '')}
              </Text>
              <Text style={styles.profileStatLabel}>Risk Profile</Text>
            </View>
          </View>
        </View>

        {/* Watchlist */}
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>Watchlist ({watchlist.length})</Text>
          <TouchableOpacity 
            style={styles.addButton}
            onPress={() => setAddWatchlistModal(true)}
          >
            <Ionicons name="add" size={20} color="#fff" />
          </TouchableOpacity>
        </View>

        {watchlist.length > 0 ? (
          watchlist.map(renderWatchlistItem)
        ) : (
          <View style={styles.emptyCard}>
            <Ionicons name="eye-outline" size={32} color="#6b7280" />
            <Text style={styles.emptyText}>No items in watchlist</Text>
            <Text style={styles.emptySubtext}>Add assets to track them</Text>
          </View>
        )}

        {/* Education */}
        <Text style={[styles.sectionTitle, { marginTop: 24, marginBottom: 16 }]}>Learn</Text>
        <View style={styles.tipsGrid}>
          {tips.map((tip) => (
            <TouchableOpacity 
              key={tip.id} 
              style={styles.tipCard}
              onPress={() => setTipModal(tip)}
            >
              <Ionicons 
                name={getTipIcon(tip.category) as any} 
                size={24} 
                color="#6366f1" 
              />
              <Text style={styles.tipTitle} numberOfLines={2}>{tip.title}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Settings */}
        <Text style={[styles.sectionTitle, { marginTop: 24, marginBottom: 16 }]}>Settings</Text>
        <View style={styles.settingsCard}>
          <TouchableOpacity style={styles.settingItem}>
            <Ionicons name="notifications-outline" size={24} color="#9ca3af" />
            <Text style={styles.settingText}>Notifications</Text>
            <Ionicons name="chevron-forward" size={20} color="#6b7280" />
          </TouchableOpacity>
          <TouchableOpacity style={styles.settingItem}>
            <Ionicons name="shield-checkmark-outline" size={24} color="#9ca3af" />
            <Text style={styles.settingText}>Privacy</Text>
            <Ionicons name="chevron-forward" size={20} color="#6b7280" />
          </TouchableOpacity>
          <TouchableOpacity style={styles.settingItem}>
            <Ionicons name="help-circle-outline" size={24} color="#9ca3af" />
            <Text style={styles.settingText}>Help & Support</Text>
            <Ionicons name="chevron-forward" size={20} color="#6b7280" />
          </TouchableOpacity>
        </View>

        {/* Logout */}
        <TouchableOpacity style={styles.logoutButton} onPress={handleLogout}>
          <Ionicons name="log-out-outline" size={20} color="#ef4444" />
          <Text style={styles.logoutText}>Logout</Text>
        </TouchableOpacity>

        {/* Version */}
        <Text style={styles.versionText}>Version 1.0.0 • Educational Use Only</Text>
      </ScrollView>

      {/* Add Watchlist Modal */}
      <Modal
        visible={addWatchlistModal}
        animationType="slide"
        transparent={true}
        onRequestClose={() => setAddWatchlistModal(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Add to Watchlist</Text>
              <TouchableOpacity onPress={() => setAddWatchlistModal(false)}>
                <Ionicons name="close" size={24} color="#fff" />
              </TouchableOpacity>
            </View>

            <View style={styles.modalBody}>
              <View style={styles.toggleContainer}>
                <TouchableOpacity
                  style={[styles.toggleButton, newAsset.type === 'crypto' && styles.toggleActive]}
                  onPress={() => setNewAsset({ ...newAsset, type: 'crypto' })}
                >
                  <Text style={[styles.toggleText, newAsset.type === 'crypto' && styles.toggleTextActive]}>
                    Crypto
                  </Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.toggleButton, newAsset.type === 'stock' && styles.toggleActive]}
                  onPress={() => setNewAsset({ ...newAsset, type: 'stock' })}
                >
                  <Text style={[styles.toggleText, newAsset.type === 'stock' && styles.toggleTextActive]}>
                    Stock
                  </Text>
                </TouchableOpacity>
              </View>

              <View style={styles.inputGroup}>
                <Text style={styles.inputLabel}>Symbol</Text>
                <TextInput
                  style={styles.input}
                  value={newAsset.symbol}
                  onChangeText={(text) => setNewAsset({ ...newAsset, symbol: text })}
                  placeholder="e.g., BTC, TCS"
                  placeholderTextColor="#6b7280"
                  autoCapitalize="characters"
                />
              </View>

              <View style={styles.inputGroup}>
                <Text style={styles.inputLabel}>Name</Text>
                <TextInput
                  style={styles.input}
                  value={newAsset.name}
                  onChangeText={(text) => setNewAsset({ ...newAsset, name: text })}
                  placeholder="e.g., Bitcoin, Tata Consultancy"
                  placeholderTextColor="#6b7280"
                />
              </View>

              <TouchableOpacity
                style={styles.submitButton}
                onPress={addToWatchlist}
                disabled={submitting}
              >
                {submitting ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <Text style={styles.submitButtonText}>Add to Watchlist</Text>
                )}
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* Education Tip Modal */}
      <Modal
        visible={!!tipModal}
        animationType="fade"
        transparent={true}
        onRequestClose={() => setTipModal(null)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.tipModalContent}>
            <TouchableOpacity 
              style={styles.tipModalClose}
              onPress={() => setTipModal(null)}
            >
              <Ionicons name="close" size={24} color="#fff" />
            </TouchableOpacity>
            <Ionicons 
              name={getTipIcon(tipModal?.category || '') as any} 
              size={48} 
              color="#6366f1" 
            />
            <Text style={styles.tipModalTitle}>{tipModal?.title}</Text>
            <Text style={styles.tipModalContent}>{tipModal?.content}</Text>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f23',
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  scrollView: {
    flex: 1,
  },
  content: {
    padding: 20,
  },
  profileCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 16,
    padding: 20,
    marginBottom: 24,
  },
  profileHeader: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  avatar: {
    width: 64,
    height: 64,
    borderRadius: 32,
  },
  avatarPlaceholder: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: 'rgba(99, 102, 241, 0.2)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  profileInfo: {
    marginLeft: 16,
    flex: 1,
  },
  profileName: {
    color: '#fff',
    fontSize: 20,
    fontWeight: '700',
  },
  profileEmail: {
    color: '#9ca3af',
    fontSize: 14,
    marginTop: 4,
  },
  profileStats: {
    flexDirection: 'row',
    marginTop: 20,
    paddingTop: 20,
    borderTopWidth: 1,
    borderTopColor: '#2d2d44',
  },
  profileStatItem: {
    flex: 1,
    alignItems: 'center',
  },
  profileStatDivider: {
    width: 1,
    backgroundColor: '#2d2d44',
  },
  profileStatValue: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '700',
  },
  profileStatLabel: {
    color: '#6b7280',
    fontSize: 12,
    marginTop: 4,
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  sectionTitle: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '600',
  },
  addButton: {
    backgroundColor: '#6366f1',
    width: 36,
    height: 36,
    borderRadius: 18,
    justifyContent: 'center',
    alignItems: 'center',
  },
  watchlistCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
  },
  watchlistInfo: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  watchlistHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  watchlistNameContainer: {
    marginLeft: 12,
    flex: 1,
  },
  watchlistSymbol: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  watchlistName: {
    color: '#9ca3af',
    fontSize: 12,
    marginTop: 2,
  },
  watchlistPriceContainer: {
    alignItems: 'flex-end',
  },
  watchlistPrice: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  watchlistChange: {
    fontSize: 13,
    marginTop: 2,
  },
  watchlistFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#2d2d44',
  },
  aiScoreBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(99, 102, 241, 0.2)',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  aiScoreText: {
    color: '#6366f1',
    fontSize: 12,
    marginLeft: 4,
    fontWeight: '500',
  },
  emptyCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    padding: 32,
    alignItems: 'center',
  },
  emptyText: {
    color: '#fff',
    fontSize: 16,
    marginTop: 12,
  },
  emptySubtext: {
    color: '#6b7280',
    fontSize: 14,
    marginTop: 4,
  },
  tipsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginHorizontal: -6,
  },
  tipCard: {
    width: '46%',
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    padding: 16,
    margin: 6,
    alignItems: 'center',
  },
  tipTitle: {
    color: '#fff',
    fontSize: 13,
    textAlign: 'center',
    marginTop: 12,
  },
  settingsCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    overflow: 'hidden',
  },
  settingItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#2d2d44',
  },
  settingText: {
    color: '#fff',
    fontSize: 16,
    marginLeft: 16,
    flex: 1,
  },
  logoutButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(239, 68, 68, 0.1)',
    padding: 16,
    borderRadius: 12,
    marginTop: 24,
  },
  logoutText: {
    color: '#ef4444',
    fontSize: 16,
    fontWeight: '600',
    marginLeft: 8,
  },
  versionText: {
    color: '#6b7280',
    fontSize: 12,
    textAlign: 'center',
    marginTop: 24,
    marginBottom: 20,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.7)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: '#1a1a2e',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 20,
    borderBottomWidth: 1,
    borderBottomColor: '#2d2d44',
  },
  modalTitle: {
    color: '#fff',
    fontSize: 20,
    fontWeight: '700',
  },
  modalBody: {
    padding: 20,
  },
  toggleContainer: {
    flexDirection: 'row',
    marginBottom: 16,
  },
  toggleButton: {
    flex: 1,
    paddingVertical: 12,
    alignItems: 'center',
    backgroundColor: '#0f0f23',
    marginHorizontal: 4,
    borderRadius: 8,
  },
  toggleActive: {
    backgroundColor: '#6366f1',
  },
  toggleText: {
    color: '#9ca3af',
    fontWeight: '500',
  },
  toggleTextActive: {
    color: '#fff',
  },
  inputGroup: {
    marginBottom: 16,
  },
  inputLabel: {
    color: '#9ca3af',
    fontSize: 14,
    marginBottom: 8,
  },
  input: {
    backgroundColor: '#0f0f23',
    borderRadius: 12,
    padding: 16,
    color: '#fff',
    fontSize: 16,
  },
  submitButton: {
    backgroundColor: '#6366f1',
    paddingVertical: 16,
    borderRadius: 12,
    alignItems: 'center',
    marginTop: 8,
  },
  submitButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  tipModalContent: {
    backgroundColor: '#1a1a2e',
    borderRadius: 16,
    padding: 24,
    margin: 20,
    alignItems: 'center',
  },
  tipModalClose: {
    position: 'absolute',
    top: 16,
    right: 16,
  },
  tipModalTitle: {
    color: '#fff',
    fontSize: 20,
    fontWeight: '700',
    textAlign: 'center',
    marginTop: 16,
    marginBottom: 16,
  },
  tipModalContent: {
    color: '#d1d5db',
    fontSize: 14,
    lineHeight: 22,
    textAlign: 'center',
  },
});
