import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
  Modal,
  Alert,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../../src/services/api';

interface Asset {
  symbol: string;
  name: string;
  price_inr: number;
  change_24h: number;
  rsi?: number;
  pe_ratio?: number;
}

interface Holding {
  asset_type: string;
  asset_symbol: string;
  asset_name: string;
  quantity: number;
  avg_price: number;
  current_price: number;
  current_value: number;
  pnl: number;
  pnl_pct: number;
}

interface Summary {
  total_value: number;
  total_invested: number;
  total_pnl: number;
  total_pnl_pct: number;
  num_holdings: number;
}

export default function SimulatorScreen() {
  const [activeTab, setActiveTab] = useState<'trade' | 'portfolio'>('trade');
  const [assetType, setAssetType] = useState<'crypto' | 'stocks'>('crypto');
  const [assets, setAssets] = useState<Record<string, Asset>>({});
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [tradeModalVisible, setTradeModalVisible] = useState(false);
  const [selectedAsset, setSelectedAsset] = useState<Asset | null>(null);
  const [tradeType, setTradeType] = useState<'buy' | 'sell'>('buy');
  const [quantity, setQuantity] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetchData();
  }, [assetType]);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [pricesRes, portfolioRes]: any[] = await Promise.all([
        assetType === 'crypto' ? api.getCryptoPrices() : api.getStockPrices(),
        api.getSimulatorPortfolio(),
      ]);
      setAssets(pricesRes.data || {});
      setHoldings(portfolioRes.holdings || []);
      setSummary(portfolioRes.summary || null);
    } catch (error) {
      console.error('Error fetching data:', error);
    } finally {
      setLoading(false);
    }
  };

  const openTradeModal = (asset: Asset, type: 'buy' | 'sell') => {
    setSelectedAsset(asset);
    setTradeType(type);
    setQuantity('');
    setTradeModalVisible(true);
  };

  const executeTrade = async () => {
    if (!selectedAsset || !quantity || parseFloat(quantity) <= 0) {
      Alert.alert('Error', 'Please enter a valid quantity');
      return;
    }

    try {
      setSubmitting(true);
      await api.executeVirtualTrade({
        asset_type: assetType,
        asset_symbol: selectedAsset.symbol,
        asset_name: selectedAsset.name,
        quantity: parseFloat(quantity),
        price_inr: selectedAsset.price_inr,
        trade_type: tradeType,
        is_virtual: true,
      });
      
      setTradeModalVisible(false);
      Alert.alert(
        'Trade Executed',
        `Successfully ${tradeType === 'buy' ? 'bought' : 'sold'} ${quantity} ${selectedAsset.symbol}`,
        [{ text: 'OK', onPress: fetchData }]
      );
    } catch (error: any) {
      Alert.alert('Error', error.message || 'Failed to execute trade');
    } finally {
      setSubmitting(false);
    }
  };

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0,
    }).format(value);
  };

  const calculateTotalValue = () => {
    if (!selectedAsset || !quantity) return 0;
    return parseFloat(quantity) * selectedAsset.price_inr;
  };

  const renderAssetCard = (symbol: string, data: Asset) => (
    <View key={symbol} style={styles.assetCard}>
      <View style={styles.assetInfo}>
        <View style={styles.assetHeader}>
          <Ionicons 
            name={assetType === 'crypto' ? 'logo-bitcoin' : 'business'} 
            size={24} 
            color={assetType === 'crypto' ? '#f7931a' : '#3b82f6'} 
          />
          <View style={styles.assetNameContainer}>
            <Text style={styles.assetSymbol}>{symbol}</Text>
            <Text style={styles.assetName} numberOfLines={1}>{data.name}</Text>
          </View>
        </View>
        <View style={styles.assetPriceContainer}>
          <Text style={styles.assetPrice}>{formatCurrency(data.price_inr)}</Text>
          <Text style={[
            styles.assetChange,
            { color: data.change_24h >= 0 ? '#10b981' : '#ef4444' }
          ]}>
            {data.change_24h >= 0 ? '+' : ''}{data.change_24h.toFixed(2)}%
          </Text>
        </View>
      </View>
      <View style={styles.assetMeta}>
        {data.rsi && <Text style={styles.metaText}>RSI: {data.rsi}</Text>}
        {data.pe_ratio && <Text style={styles.metaText}>P/E: {data.pe_ratio}</Text>}
      </View>
      <View style={styles.tradeButtons}>
        <TouchableOpacity
          style={[styles.tradeButton, styles.buyButton]}
          onPress={() => openTradeModal({ symbol, ...data }, 'buy')}
        >
          <Text style={styles.tradeButtonText}>BUY</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.tradeButton, styles.sellButton]}
          onPress={() => openTradeModal({ symbol, ...data }, 'sell')}
        >
          <Text style={styles.tradeButtonText}>SELL</Text>
        </TouchableOpacity>
      </View>
    </View>
  );

  const renderHoldingCard = (holding: Holding) => (
    <View key={`${holding.asset_type}_${holding.asset_symbol}`} style={styles.holdingCard}>
      <View style={styles.holdingHeader}>
        <View style={styles.holdingInfo}>
          <Ionicons 
            name={holding.asset_type === 'crypto' ? 'logo-bitcoin' : 'business'} 
            size={20} 
            color={holding.asset_type === 'crypto' ? '#f7931a' : '#3b82f6'} 
          />
          <Text style={styles.holdingSymbol}>{holding.asset_symbol}</Text>
        </View>
        <Text style={[
          styles.holdingPnl,
          { color: holding.pnl >= 0 ? '#10b981' : '#ef4444' }
        ]}>
          {holding.pnl >= 0 ? '+' : ''}{formatCurrency(holding.pnl)} ({holding.pnl_pct.toFixed(2)}%)
        </Text>
      </View>
      <View style={styles.holdingDetails}>
        <View style={styles.holdingDetailItem}>
          <Text style={styles.holdingDetailLabel}>Qty</Text>
          <Text style={styles.holdingDetailValue}>{holding.quantity.toFixed(4)}</Text>
        </View>
        <View style={styles.holdingDetailItem}>
          <Text style={styles.holdingDetailLabel}>Avg Price</Text>
          <Text style={styles.holdingDetailValue}>{formatCurrency(holding.avg_price)}</Text>
        </View>
        <View style={styles.holdingDetailItem}>
          <Text style={styles.holdingDetailLabel}>Current</Text>
          <Text style={styles.holdingDetailValue}>{formatCurrency(holding.current_value)}</Text>
        </View>
      </View>
    </View>
  );

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Trading Simulator</Text>
        <Text style={styles.headerSubtitle}>Practice with virtual money</Text>
      </View>

      {/* Tabs */}
      <View style={styles.tabContainer}>
        <TouchableOpacity
          style={[styles.tab, activeTab === 'trade' && styles.activeTab]}
          onPress={() => setActiveTab('trade')}
        >
          <Ionicons 
            name="swap-horizontal" 
            size={20} 
            color={activeTab === 'trade' ? '#6366f1' : '#6b7280'} 
          />
          <Text style={[styles.tabText, activeTab === 'trade' && styles.activeTabText]}>Trade</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.tab, activeTab === 'portfolio' && styles.activeTab]}
          onPress={() => setActiveTab('portfolio')}
        >
          <Ionicons 
            name="pie-chart" 
            size={20} 
            color={activeTab === 'portfolio' ? '#6366f1' : '#6b7280'} 
          />
          <Text style={[styles.tabText, activeTab === 'portfolio' && styles.activeTabText]}>Portfolio</Text>
        </TouchableOpacity>
      </View>

      {activeTab === 'trade' && (
        <>
          {/* Asset Type Toggle */}
          <View style={styles.assetTypeContainer}>
            <TouchableOpacity
              style={[styles.assetTypeButton, assetType === 'crypto' && styles.assetTypeActive]}
              onPress={() => setAssetType('crypto')}
            >
              <Ionicons name="logo-bitcoin" size={16} color={assetType === 'crypto' ? '#fff' : '#9ca3af'} />
              <Text style={[styles.assetTypeText, assetType === 'crypto' && styles.assetTypeTextActive]}>
                Crypto
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.assetTypeButton, assetType === 'stocks' && styles.assetTypeActive]}
              onPress={() => setAssetType('stocks')}
            >
              <Ionicons name="trending-up" size={16} color={assetType === 'stocks' ? '#fff' : '#9ca3af'} />
              <Text style={[styles.assetTypeText, assetType === 'stocks' && styles.assetTypeTextActive]}>
                Stocks
              </Text>
            </TouchableOpacity>
          </View>

          {loading ? (
            <View style={styles.loadingContainer}>
              <ActivityIndicator size="large" color="#6366f1" />
            </View>
          ) : (
            <ScrollView style={styles.assetList} contentContainerStyle={styles.assetListContent}>
              {Object.entries(assets).map(([symbol, data]) => renderAssetCard(symbol, data as Asset))}
            </ScrollView>
          )}
        </>
      )}

      {activeTab === 'portfolio' && (
        <ScrollView style={styles.portfolioContainer} contentContainerStyle={styles.portfolioContent}>
          {/* Summary Card */}
          {summary && (
            <View style={styles.summaryCard}>
              <Text style={styles.summaryTitle}>Virtual Portfolio</Text>
              <Text style={styles.summaryValue}>{formatCurrency(summary.total_value)}</Text>
              <View style={styles.summaryStats}>
                <View style={styles.summaryStatItem}>
                  <Text style={styles.summaryStatLabel}>Invested</Text>
                  <Text style={styles.summaryStatValue}>{formatCurrency(summary.total_invested)}</Text>
                </View>
                <View style={styles.summaryStatItem}>
                  <Text style={styles.summaryStatLabel}>P&L</Text>
                  <Text style={[
                    styles.summaryStatValue,
                    { color: summary.total_pnl >= 0 ? '#10b981' : '#ef4444' }
                  ]}>
                    {summary.total_pnl >= 0 ? '+' : ''}{formatCurrency(summary.total_pnl)} ({summary.total_pnl_pct.toFixed(2)}%)
                  </Text>
                </View>
              </View>
            </View>
          )}

          {/* Holdings */}
          <Text style={styles.sectionTitle}>Holdings ({holdings.length})</Text>
          {holdings.length > 0 ? (
            holdings.map(renderHoldingCard)
          ) : (
            <View style={styles.emptyState}>
              <Ionicons name="wallet-outline" size={48} color="#6b7280" />
              <Text style={styles.emptyText}>No holdings yet</Text>
              <Text style={styles.emptySubtext}>Start trading to build your portfolio</Text>
            </View>
          )}
        </ScrollView>
      )}

      {/* Trade Modal */}
      <Modal
        visible={tradeModalVisible}
        animationType="slide"
        transparent={true}
        onRequestClose={() => setTradeModalVisible(false)}
      >
        <KeyboardAvoidingView 
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          style={styles.modalOverlay}
        >
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>
                {tradeType === 'buy' ? 'Buy' : 'Sell'} {selectedAsset?.symbol}
              </Text>
              <TouchableOpacity onPress={() => setTradeModalVisible(false)}>
                <Ionicons name="close" size={24} color="#fff" />
              </TouchableOpacity>
            </View>

            <View style={styles.modalBody}>
              <View style={styles.priceInfo}>
                <Text style={styles.priceLabel}>Current Price</Text>
                <Text style={styles.priceValue}>{formatCurrency(selectedAsset?.price_inr || 0)}</Text>
              </View>

              <View style={styles.inputGroup}>
                <Text style={styles.inputLabel}>Quantity</Text>
                <TextInput
                  style={styles.input}
                  value={quantity}
                  onChangeText={setQuantity}
                  keyboardType="decimal-pad"
                  placeholder="0.00"
                  placeholderTextColor="#6b7280"
                />
              </View>

              <View style={styles.totalContainer}>
                <Text style={styles.totalLabel}>Total Value</Text>
                <Text style={styles.totalValue}>{formatCurrency(calculateTotalValue())}</Text>
              </View>

              <View style={styles.riskNote}>
                <Ionicons name="information-circle" size={16} color="#f59e0b" />
                <Text style={styles.riskNoteText}>
                  Max 5% of portfolio per trade recommended. Auto stop-loss at 10%.
                </Text>
              </View>

              <TouchableOpacity
                style={[
                  styles.executeButton,
                  tradeType === 'buy' ? styles.executeBuy : styles.executeSell
                ]}
                onPress={executeTrade}
                disabled={submitting}
              >
                {submitting ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <Text style={styles.executeButtonText}>
                    {tradeType === 'buy' ? 'Confirm Buy' : 'Confirm Sell'}
                  </Text>
                )}
              </TouchableOpacity>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f23',
  },
  header: {
    paddingHorizontal: 20,
    paddingTop: 8,
    paddingBottom: 16,
  },
  headerTitle: {
    fontSize: 28,
    fontWeight: '700',
    color: '#fff',
  },
  headerSubtitle: {
    fontSize: 14,
    color: '#9ca3af',
    marginTop: 4,
  },
  tabContainer: {
    flexDirection: 'row',
    paddingHorizontal: 20,
    marginBottom: 16,
  },
  tab: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    backgroundColor: '#1a1a2e',
    marginHorizontal: 4,
    borderRadius: 12,
  },
  activeTab: {
    backgroundColor: 'rgba(99, 102, 241, 0.2)',
  },
  tabText: {
    color: '#6b7280',
    marginLeft: 8,
    fontWeight: '500',
  },
  activeTabText: {
    color: '#6366f1',
  },
  assetTypeContainer: {
    flexDirection: 'row',
    paddingHorizontal: 20,
    marginBottom: 16,
  },
  assetTypeButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: 20,
    backgroundColor: '#1a1a2e',
    marginRight: 12,
  },
  assetTypeActive: {
    backgroundColor: '#6366f1',
  },
  assetTypeText: {
    color: '#9ca3af',
    marginLeft: 6,
    fontWeight: '500',
  },
  assetTypeTextActive: {
    color: '#fff',
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  assetList: {
    flex: 1,
  },
  assetListContent: {
    padding: 20,
    paddingTop: 0,
  },
  assetCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 16,
    padding: 16,
    marginBottom: 12,
  },
  assetInfo: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  assetHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  assetNameContainer: {
    marginLeft: 12,
    flex: 1,
  },
  assetSymbol: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '700',
  },
  assetName: {
    color: '#9ca3af',
    fontSize: 12,
    marginTop: 2,
  },
  assetPriceContainer: {
    alignItems: 'flex-end',
  },
  assetPrice: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  assetChange: {
    fontSize: 13,
    marginTop: 2,
  },
  assetMeta: {
    flexDirection: 'row',
    marginTop: 8,
  },
  metaText: {
    color: '#6b7280',
    fontSize: 12,
    marginRight: 16,
  },
  tradeButtons: {
    flexDirection: 'row',
    marginTop: 12,
  },
  tradeButton: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 8,
    alignItems: 'center',
  },
  buyButton: {
    backgroundColor: 'rgba(16, 185, 129, 0.2)',
    marginRight: 8,
  },
  sellButton: {
    backgroundColor: 'rgba(239, 68, 68, 0.2)',
  },
  tradeButtonText: {
    fontWeight: '600',
    fontSize: 14,
    color: '#fff',
  },
  portfolioContainer: {
    flex: 1,
  },
  portfolioContent: {
    padding: 20,
  },
  summaryCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 16,
    padding: 20,
    marginBottom: 20,
  },
  summaryTitle: {
    color: '#9ca3af',
    fontSize: 14,
  },
  summaryValue: {
    color: '#fff',
    fontSize: 32,
    fontWeight: '700',
    marginTop: 8,
  },
  summaryStats: {
    flexDirection: 'row',
    marginTop: 16,
  },
  summaryStatItem: {
    flex: 1,
  },
  summaryStatLabel: {
    color: '#6b7280',
    fontSize: 12,
  },
  summaryStatValue: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
    marginTop: 4,
  },
  sectionTitle: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '600',
    marginBottom: 12,
  },
  holdingCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
  },
  holdingHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  holdingInfo: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  holdingSymbol: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
    marginLeft: 8,
  },
  holdingPnl: {
    fontSize: 14,
    fontWeight: '600',
  },
  holdingDetails: {
    flexDirection: 'row',
    marginTop: 12,
  },
  holdingDetailItem: {
    flex: 1,
  },
  holdingDetailLabel: {
    color: '#6b7280',
    fontSize: 11,
  },
  holdingDetailValue: {
    color: '#fff',
    fontSize: 14,
    marginTop: 2,
  },
  emptyState: {
    alignItems: 'center',
    paddingTop: 40,
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
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.7)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: '#1a1a2e',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    padding: 20,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 20,
  },
  modalTitle: {
    color: '#fff',
    fontSize: 20,
    fontWeight: '700',
  },
  modalBody: {},
  priceInfo: {
    backgroundColor: '#0f0f23',
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
  },
  priceLabel: {
    color: '#9ca3af',
    fontSize: 12,
  },
  priceValue: {
    color: '#fff',
    fontSize: 24,
    fontWeight: '700',
    marginTop: 4,
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
    fontSize: 18,
  },
  totalContainer: {
    backgroundColor: '#0f0f23',
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
  },
  totalLabel: {
    color: '#9ca3af',
    fontSize: 12,
  },
  totalValue: {
    color: '#fff',
    fontSize: 24,
    fontWeight: '700',
    marginTop: 4,
  },
  riskNote: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: 'rgba(245, 158, 11, 0.1)',
    borderRadius: 12,
    padding: 12,
    marginBottom: 20,
  },
  riskNoteText: {
    color: '#f59e0b',
    fontSize: 12,
    marginLeft: 8,
    flex: 1,
  },
  executeButton: {
    paddingVertical: 16,
    borderRadius: 12,
    alignItems: 'center',
  },
  executeBuy: {
    backgroundColor: '#10b981',
  },
  executeSell: {
    backgroundColor: '#ef4444',
  },
  executeButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
});
