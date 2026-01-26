import React, { useState, useEffect, useCallback } from 'react';
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
  Dimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../../src/services/api';

const { width } = Dimensions.get('window');

interface Holding {
  asset_type: string;
  asset_symbol: string;
  asset_name: string;
  quantity: number;
  avg_price: number;
  current_price: number;
  current_value: number;
  total_invested: number;
  pnl: number;
  pnl_pct: number;
}

interface PortfolioAnalysis {
  summary: string;
  suggestions: string[];
  risk_score: number;
  diversification_score: number;
  metrics: {
    total_value: number;
    crypto_allocation: number;
    stock_allocation: number;
    num_holdings: number;
  };
}

interface Summary {
  total_value: number;
  total_invested: number;
  total_pnl: number;
  total_pnl_pct: number;
  num_holdings: number;
}

export default function PortfolioScreen() {
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [analysis, setAnalysis] = useState<PortfolioAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [addModalVisible, setAddModalVisible] = useState(false);
  const [tradeType, setTradeType] = useState<'buy' | 'sell'>('buy');
  const [assetType, setAssetType] = useState<'crypto' | 'stock'>('crypto');
  const [symbol, setSymbol] = useState('');
  const [assetName, setAssetName] = useState('');
  const [quantity, setQuantity] = useState('');
  const [price, setPrice] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetchPortfolio();
  }, []);

  const fetchPortfolio = async () => {
    try {
      setLoading(true);
      const response: any = await api.getPortfolio();
      setHoldings(response.holdings || []);
      setSummary(response.summary || null);
      setAnalysis(response.analysis || null);
    } catch (error) {
      console.error('Error fetching portfolio:', error);
    } finally {
      setLoading(false);
    }
  };

  const addTrade = async () => {
    if (!symbol || !assetName || !quantity || !price) {
      Alert.alert('Error', 'Please fill all fields');
      return;
    }

    try {
      setSubmitting(true);
      await api.addPortfolioTrade({
        asset_type: assetType,
        asset_symbol: symbol.toUpperCase(),
        asset_name: assetName,
        quantity: parseFloat(quantity),
        price_inr: parseFloat(price),
        trade_type: tradeType,
        is_virtual: false,
      });
      
      setAddModalVisible(false);
      resetForm();
      Alert.alert('Success', 'Trade added successfully', [{ text: 'OK', onPress: fetchPortfolio }]);
    } catch (error: any) {
      Alert.alert('Error', error.message || 'Failed to add trade');
    } finally {
      setSubmitting(false);
    }
  };

  const resetForm = () => {
    setSymbol('');
    setAssetName('');
    setQuantity('');
    setPrice('');
    setTradeType('buy');
    setAssetType('crypto');
  };

  const exportPortfolio = async () => {
    try {
      const response: any = await api.exportPortfolio();
      Alert.alert(
        'Export Ready',
        `${response.data.length} trades ready for export.\n\nTax Notes:\n- Crypto: ${response.tax_notes.crypto_tax}\n- Stock LTCG: ${response.tax_notes.stock_ltcg}`,
        [{ text: 'OK' }]
      );
    } catch (error) {
      Alert.alert('Error', 'Failed to export portfolio');
    }
  };

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0,
    }).format(value);
  };

  const renderScoreBar = (score: number, label: string, color: string) => (
    <View style={styles.scoreItem}>
      <View style={styles.scoreHeader}>
        <Text style={styles.scoreLabel}>{label}</Text>
        <Text style={[styles.scoreValue, { color }]}>{score}/100</Text>
      </View>
      <View style={styles.scoreTrack}>
        <View style={[styles.scoreFill, { width: `${score}%`, backgroundColor: color }]} />
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
          <View style={styles.holdingNameContainer}>
            <Text style={styles.holdingSymbol}>{holding.asset_symbol}</Text>
            <Text style={styles.holdingName} numberOfLines={1}>{holding.asset_name}</Text>
          </View>
        </View>
        <View style={styles.holdingValueContainer}>
          <Text style={styles.holdingValue}>{formatCurrency(holding.current_value)}</Text>
          <Text style={[
            styles.holdingPnl,
            { color: holding.pnl >= 0 ? '#10b981' : '#ef4444' }
          ]}>
            {holding.pnl >= 0 ? '+' : ''}{holding.pnl_pct.toFixed(1)}%
          </Text>
        </View>
      </View>
      <View style={styles.holdingDetails}>
        <View style={styles.holdingDetailItem}>
          <Text style={styles.holdingDetailLabel}>Qty</Text>
          <Text style={styles.holdingDetailValue}>{holding.quantity}</Text>
        </View>
        <View style={styles.holdingDetailItem}>
          <Text style={styles.holdingDetailLabel}>Avg Buy</Text>
          <Text style={styles.holdingDetailValue}>{formatCurrency(holding.avg_price)}</Text>
        </View>
        <View style={styles.holdingDetailItem}>
          <Text style={styles.holdingDetailLabel}>P&L</Text>
          <Text style={[
            styles.holdingDetailValue,
            { color: holding.pnl >= 0 ? '#10b981' : '#ef4444' }
          ]}>
            {holding.pnl >= 0 ? '+' : ''}{formatCurrency(holding.pnl)}
          </Text>
        </View>
      </View>
    </View>
  );

  // Simple allocation chart
  const renderAllocationChart = () => {
    const cryptoHoldings = holdings.filter(h => h.asset_type === 'crypto');
    const stockHoldings = holdings.filter(h => h.asset_type === 'stock');
    const cryptoValue = cryptoHoldings.reduce((sum, h) => sum + h.current_value, 0);
    const stockValue = stockHoldings.reduce((sum, h) => sum + h.current_value, 0);
    const total = cryptoValue + stockValue;
    
    if (total === 0) return null;
    
    const cryptoPct = (cryptoValue / total) * 100;
    const stockPct = (stockValue / total) * 100;

    return (
      <View style={styles.chartContainer}>
        <Text style={styles.chartTitle}>Asset Allocation</Text>
        <View style={styles.allocationBar}>
          <View style={[styles.allocationSegment, { width: `${cryptoPct}%`, backgroundColor: '#f7931a' }]} />
          <View style={[styles.allocationSegment, { width: `${stockPct}%`, backgroundColor: '#3b82f6' }]} />
        </View>
        <View style={styles.allocationLegend}>
          <View style={styles.legendItem}>
            <View style={[styles.legendDot, { backgroundColor: '#f7931a' }]} />
            <Text style={styles.legendText}>Crypto {cryptoPct.toFixed(1)}%</Text>
          </View>
          <View style={styles.legendItem}>
            <View style={[styles.legendDot, { backgroundColor: '#3b82f6' }]} />
            <Text style={styles.legendText}>Stocks {stockPct.toFixed(1)}%</Text>
          </View>
        </View>
      </View>
    );
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
        <View style={styles.header}>
          <View>
            <Text style={styles.headerTitle}>Portfolio</Text>
            <Text style={styles.headerSubtitle}>Track your real investments</Text>
          </View>
          <TouchableOpacity style={styles.exportButton} onPress={exportPortfolio}>
            <Ionicons name="download-outline" size={20} color="#6366f1" />
          </TouchableOpacity>
        </View>

        {/* Summary Card */}
        {summary && (
          <View style={styles.summaryCard}>
            <Text style={styles.summaryLabel}>Total Value</Text>
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
                  {summary.total_pnl >= 0 ? '+' : ''}{formatCurrency(summary.total_pnl)}
                </Text>
              </View>
              <View style={styles.summaryStatItem}>
                <Text style={styles.summaryStatLabel}>Return</Text>
                <Text style={[
                  styles.summaryStatValue,
                  { color: summary.total_pnl_pct >= 0 ? '#10b981' : '#ef4444' }
                ]}>
                  {summary.total_pnl_pct >= 0 ? '+' : ''}{summary.total_pnl_pct.toFixed(2)}%
                </Text>
              </View>
            </View>
          </View>
        )}

        {/* Allocation Chart */}
        {holdings.length > 0 && renderAllocationChart()}

        {/* AI Analysis */}
        {analysis && (
          <View style={styles.analysisCard}>
            <View style={styles.analysisHeader}>
              <Ionicons name="sparkles" size={20} color="#6366f1" />
              <Text style={styles.analysisTitle}>AI Analysis</Text>
            </View>
            <Text style={styles.analysisSummary}>{analysis.summary}</Text>
            
            <View style={styles.scoresContainer}>
              {renderScoreBar(analysis.risk_score, 'Risk Score', analysis.risk_score > 70 ? '#ef4444' : analysis.risk_score > 40 ? '#f59e0b' : '#10b981')}
              {renderScoreBar(analysis.diversification_score, 'Diversification', analysis.diversification_score > 60 ? '#10b981' : analysis.diversification_score > 30 ? '#f59e0b' : '#ef4444')}
            </View>

            {analysis.suggestions.length > 0 && (
              <View style={styles.suggestionsContainer}>
                <Text style={styles.suggestionsTitle}>Suggestions</Text>
                {analysis.suggestions.map((suggestion, index) => (
                  <View key={index} style={styles.suggestionItem}>
                    <Ionicons name="bulb" size={14} color="#f59e0b" />
                    <Text style={styles.suggestionText}>{suggestion}</Text>
                  </View>
                ))}
              </View>
            )}
          </View>
        )}

        {/* Holdings */}
        <View style={styles.holdingsHeader}>
          <Text style={styles.sectionTitle}>Holdings ({holdings.length})</Text>
          <TouchableOpacity 
            style={styles.addButton}
            onPress={() => setAddModalVisible(true)}
          >
            <Ionicons name="add" size={20} color="#fff" />
            <Text style={styles.addButtonText}>Add Trade</Text>
          </TouchableOpacity>
        </View>

        {holdings.length > 0 ? (
          holdings.map(renderHoldingCard)
        ) : (
          <View style={styles.emptyState}>
            <Ionicons name="folder-open-outline" size={48} color="#6b7280" />
            <Text style={styles.emptyText}>No holdings yet</Text>
            <Text style={styles.emptySubtext}>Add your first trade to start tracking</Text>
          </View>
        )}
      </ScrollView>

      {/* Add Trade Modal */}
      <Modal
        visible={addModalVisible}
        animationType="slide"
        transparent={true}
        onRequestClose={() => setAddModalVisible(false)}
      >
        <KeyboardAvoidingView 
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          style={styles.modalOverlay}
        >
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Add Trade</Text>
              <TouchableOpacity onPress={() => { setAddModalVisible(false); resetForm(); }}>
                <Ionicons name="close" size={24} color="#fff" />
              </TouchableOpacity>
            </View>

            <ScrollView style={styles.modalBody}>
              {/* Trade Type */}
              <View style={styles.toggleContainer}>
                <TouchableOpacity
                  style={[styles.toggleButton, tradeType === 'buy' && styles.toggleActive]}
                  onPress={() => setTradeType('buy')}
                >
                  <Text style={[styles.toggleText, tradeType === 'buy' && styles.toggleTextActive]}>Buy</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.toggleButton, tradeType === 'sell' && styles.toggleActive]}
                  onPress={() => setTradeType('sell')}
                >
                  <Text style={[styles.toggleText, tradeType === 'sell' && styles.toggleTextActive]}>Sell</Text>
                </TouchableOpacity>
              </View>

              {/* Asset Type */}
              <View style={styles.toggleContainer}>
                <TouchableOpacity
                  style={[styles.toggleButton, assetType === 'crypto' && styles.toggleActive]}
                  onPress={() => setAssetType('crypto')}
                >
                  <Text style={[styles.toggleText, assetType === 'crypto' && styles.toggleTextActive]}>Crypto</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.toggleButton, assetType === 'stock' && styles.toggleActive]}
                  onPress={() => setAssetType('stock')}
                >
                  <Text style={[styles.toggleText, assetType === 'stock' && styles.toggleTextActive]}>Stock</Text>
                </TouchableOpacity>
              </View>

              <View style={styles.inputGroup}>
                <Text style={styles.inputLabel}>Symbol</Text>
                <TextInput
                  style={styles.input}
                  value={symbol}
                  onChangeText={setSymbol}
                  placeholder="e.g., BTC, TCS"
                  placeholderTextColor="#6b7280"
                  autoCapitalize="characters"
                />
              </View>

              <View style={styles.inputGroup}>
                <Text style={styles.inputLabel}>Asset Name</Text>
                <TextInput
                  style={styles.input}
                  value={assetName}
                  onChangeText={setAssetName}
                  placeholder="e.g., Bitcoin, Tata Consultancy"
                  placeholderTextColor="#6b7280"
                />
              </View>

              <View style={styles.inputRow}>
                <View style={[styles.inputGroup, { flex: 1, marginRight: 8 }]}>
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
                <View style={[styles.inputGroup, { flex: 1, marginLeft: 8 }]}>
                  <Text style={styles.inputLabel}>Price (INR)</Text>
                  <TextInput
                    style={styles.input}
                    value={price}
                    onChangeText={setPrice}
                    keyboardType="decimal-pad"
                    placeholder="0.00"
                    placeholderTextColor="#6b7280"
                  />
                </View>
              </View>

              <TouchableOpacity
                style={[styles.submitButton, tradeType === 'buy' ? styles.buyButton : styles.sellButton]}
                onPress={addTrade}
                disabled={submitting}
              >
                {submitting ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <Text style={styles.submitButtonText}>
                    Add {tradeType === 'buy' ? 'Buy' : 'Sell'} Trade
                  </Text>
                )}
              </TouchableOpacity>
            </ScrollView>
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
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 20,
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
  exportButton: {
    padding: 12,
    backgroundColor: 'rgba(99, 102, 241, 0.2)',
    borderRadius: 12,
  },
  summaryCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 16,
    padding: 20,
    marginBottom: 20,
  },
  summaryLabel: {
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
  chartContainer: {
    backgroundColor: '#1a1a2e',
    borderRadius: 16,
    padding: 20,
    marginBottom: 20,
  },
  chartTitle: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 16,
  },
  allocationBar: {
    flexDirection: 'row',
    height: 24,
    borderRadius: 12,
    overflow: 'hidden',
    backgroundColor: '#2d2d44',
  },
  allocationSegment: {
    height: '100%',
  },
  allocationLegend: {
    flexDirection: 'row',
    justifyContent: 'center',
    marginTop: 16,
  },
  legendItem: {
    flexDirection: 'row',
    alignItems: 'center',
    marginHorizontal: 16,
  },
  legendDot: {
    width: 12,
    height: 12,
    borderRadius: 6,
    marginRight: 8,
  },
  legendText: {
    color: '#9ca3af',
    fontSize: 14,
  },
  analysisCard: {
    backgroundColor: '#1a1a2e',
    borderRadius: 16,
    padding: 20,
    marginBottom: 20,
  },
  analysisHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
  },
  analysisTitle: {
    color: '#6366f1',
    fontSize: 16,
    fontWeight: '600',
    marginLeft: 8,
  },
  analysisSummary: {
    color: '#d1d5db',
    fontSize: 14,
    lineHeight: 20,
    marginBottom: 16,
  },
  scoresContainer: {
    marginBottom: 16,
  },
  scoreItem: {
    marginBottom: 12,
  },
  scoreHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 6,
  },
  scoreLabel: {
    color: '#9ca3af',
    fontSize: 13,
  },
  scoreValue: {
    fontSize: 13,
    fontWeight: '600',
  },
  scoreTrack: {
    height: 6,
    backgroundColor: '#2d2d44',
    borderRadius: 3,
    overflow: 'hidden',
  },
  scoreFill: {
    height: '100%',
    borderRadius: 3,
  },
  suggestionsContainer: {
    marginTop: 8,
  },
  suggestionsTitle: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 12,
  },
  suggestionItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: 8,
  },
  suggestionText: {
    color: '#d1d5db',
    fontSize: 13,
    marginLeft: 8,
    flex: 1,
  },
  holdingsHeader: {
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
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#6366f1',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 8,
  },
  addButtonText: {
    color: '#fff',
    fontWeight: '600',
    marginLeft: 4,
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
    alignItems: 'flex-start',
  },
  holdingInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  holdingNameContainer: {
    marginLeft: 12,
    flex: 1,
  },
  holdingSymbol: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  holdingName: {
    color: '#9ca3af',
    fontSize: 12,
    marginTop: 2,
  },
  holdingValueContainer: {
    alignItems: 'flex-end',
  },
  holdingValue: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  holdingPnl: {
    fontSize: 13,
    fontWeight: '500',
    marginTop: 2,
  },
  holdingDetails: {
    flexDirection: 'row',
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#2d2d44',
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
    maxHeight: '90%',
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
  inputRow: {
    flexDirection: 'row',
  },
  submitButton: {
    paddingVertical: 16,
    borderRadius: 12,
    alignItems: 'center',
    marginTop: 8,
  },
  buyButton: {
    backgroundColor: '#10b981',
  },
  sellButton: {
    backgroundColor: '#ef4444',
  },
  submitButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
});
